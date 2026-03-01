"""
Curated-layer snapshot and diff utilities.

A snapshot is a point-in-time frozen copy of the entire ``cases`` table
(plus denormalised tags) stored in ``curated_snapshots`` /
``snapshot_cases``.  This enables:

  * Reproducibility  – cite a snapshot ID in a paper; anyone can
    reconstruct the exact dataset via ``GET /snapshots/{id}``.
  * Diff             – ``GET /snapshots/{id}/diff`` shows precisely
    which cases were added, removed, or had fields changed since the
    previous snapshot.
  * Auditability     – every automatic snapshot is linked to the
    ``pipeline_run.run_id`` that produced it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, selectinload

from db.models import (
    Case, CaseTag, Tag,
    Document, SecondarySource,
    CuratedSnapshot, SnapshotCase,
)

logger = logging.getLogger(__name__)

# Fields copied verbatim from Case → SnapshotCase
_CASE_SCALAR_FIELDS = (
    "case_id", "case_name", "court", "filing_date", "closing_date",
    "case_status", "case_outcome", "case_type", "plaintiff", "defendant",
    "judge", "summary", "is_stub", "state", "circuit",
)


def _snapshot_row_checksum(sc_kwargs: dict, tag_values: list) -> str:
    """Stable SHA-256 of a snapshot-case dict (scalars + sorted tags)."""
    data = {k: (str(v) if v is not None else None) for k, v in sorted(sc_kwargs.items())}
    data["_tags"] = json.dumps(
        sorted(tv["tag_type"] + ":" + tv["value"] for tv in tag_values),
        ensure_ascii=False,
    )
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def take_snapshot(
    session: Session,
    label: str,
    run_id: Optional[str] = None,
    description: Optional[str] = None,
    is_auto: bool = False,
) -> CuratedSnapshot:
    """
    Freeze the current curated layer into a new ``CuratedSnapshot``.

    Loads all cases with eager-loaded tags in a single query, writes
    ``SnapshotCase`` rows in bulk, then updates the aggregate counts.

    Call ``session.commit()`` after returning if you want the outer
    transaction committed (this function does NOT commit).
    """
    logger.info("Taking curated snapshot: %r  run_id=%s  is_auto=%s", label, run_id, is_auto)

    snap = CuratedSnapshot(
        run_id=run_id,
        label=label,
        description=description,
        is_auto=is_auto,
        taken_at=datetime.now(timezone.utc),
    )
    session.add(snap)
    session.flush()  # obtain snap.id

    # Eager-load tags for all cases (one query)
    cases: List[Case] = (
        session.query(Case)
        .options(selectinload(Case.tags).selectinload(CaseTag.tag))
        .all()
    )

    snapshot_rows: List[SnapshotCase] = []
    for c in cases:
        tag_values = [
            {"tag_type": ct.tag.tag_type, "value": ct.tag.value}
            for ct in c.tags
        ]
        scalar_kwargs: Dict[str, Any] = {
            f: getattr(c, f, None) for f in _CASE_SCALAR_FIELDS
        }
        checksum = _snapshot_row_checksum(scalar_kwargs, tag_values)

        snapshot_rows.append(SnapshotCase(
            snapshot_id=snap.id,
            case_pk=c.id,
            tag_values=tag_values,
            row_checksum=checksum,
            **scalar_kwargs,
        ))

    session.bulk_save_objects(snapshot_rows)

    # Aggregate counts
    snap.case_count = len(cases)
    snap.doc_count = session.query(Document).count()
    snap.source_count = session.query(SecondarySource).count()
    snap.tag_count = session.query(Tag).count()

    logger.info(
        "Snapshot %d (%r) complete: %d cases, %d docs, %d sources, %d tags",
        snap.id, label, snap.case_count, snap.doc_count,
        snap.source_count, snap.tag_count,
    )
    return snap


# ── Diff ─────────────────────────────────────────────────────────────

def diff_snapshots(
    session: Session,
    snap_id: int,
    prev_id: Optional[int] = None,
) -> dict:
    """
    Compare snapshot *snap_id* against either *prev_id* or the
    immediately preceding snapshot.

    Returns a dict suitable for direct JSON serialisation:
    ``{snapshot_id, prev_snapshot_id, added, removed, changed, unchanged, cases}``

    ``cases`` contains only the added / removed / changed rows.
    Each changed row includes ``changed_fields: {field: {old, new}}``.
    """
    snap = session.query(CuratedSnapshot).get(snap_id)
    if snap is None:
        raise ValueError(f"Snapshot {snap_id} not found")

    if prev_id is not None:
        prev = session.query(CuratedSnapshot).get(prev_id)
        if prev is None:
            raise ValueError(f"Previous snapshot {prev_id} not found")
    else:
        prev = (
            session.query(CuratedSnapshot)
            .filter(CuratedSnapshot.id < snap_id)
            .order_by(CuratedSnapshot.id.desc())
            .first()
        )

    # Load frozen case rows for both snapshots
    new_rows: Dict[int, SnapshotCase] = {
        sc.case_pk: sc
        for sc in session.query(SnapshotCase)
        .filter(SnapshotCase.snapshot_id == snap_id)
        .all()
    }
    old_rows: Dict[int, SnapshotCase] = {}
    if prev:
        old_rows = {
            sc.case_pk: sc
            for sc in session.query(SnapshotCase)
            .filter(SnapshotCase.snapshot_id == prev.id)
            .all()
        }

    added_pks   = set(new_rows) - set(old_rows)
    removed_pks = set(old_rows) - set(new_rows)
    common_pks  = set(new_rows) & set(old_rows)

    changed_cases: List[dict] = []
    unchanged_count = 0

    for pk in common_pks:
        n = new_rows[pk]
        o = old_rows[pk]
        if n.row_checksum == o.row_checksum:
            unchanged_count += 1
            continue
        # Field-level diff
        fields_changed = {}
        for field in _CASE_SCALAR_FIELDS:
            nv = getattr(n, field, None)
            ov = getattr(o, field, None)
            if str(nv) != str(ov):
                fields_changed[field] = {"old": str(ov), "new": str(nv)}
        # Tag diff
        n_tags = set(f"{t['tag_type']}:{t['value']}" for t in (n.tag_values or []))
        o_tags = set(f"{t['tag_type']}:{t['value']}" for t in (o.tag_values or []))
        if n_tags != o_tags:
            fields_changed["tags"] = {
                "old": sorted(o_tags - n_tags),
                "new": sorted(n_tags - o_tags),
            }
        changed_cases.append({
            "case_pk": pk, "case_id": n.case_id,
            "action": "changed", "changed_fields": fields_changed,
        })

    added_list = [
        {"case_pk": pk, "case_id": new_rows[pk].case_id,
         "case_name": new_rows[pk].case_name, "action": "added"}
        for pk in added_pks
    ]
    removed_list = [
        {"case_pk": pk, "case_id": old_rows[pk].case_id,
         "case_name": old_rows[pk].case_name, "action": "removed"}
        for pk in removed_pks
    ]

    return {
        "snapshot_id":        snap_id,
        "snapshot_label":     snap.label,
        "snapshot_taken_at":  snap.taken_at.isoformat() if snap.taken_at else None,
        "prev_snapshot_id":   prev.id if prev else None,
        "prev_snapshot_label": prev.label if prev else None,
        "added_count":        len(added_pks),
        "removed_count":      len(removed_pks),
        "changed_count":      len(changed_cases),
        "unchanged_count":    unchanged_count,
        "cases":              added_list + removed_list + changed_cases,
    }
