"""
Data Versioning API – list, inspect, and diff curated-layer snapshots.

A snapshot is a point-in-time frozen copy of the entire cases table.
Snapshots are taken automatically after every successful pipeline run and
can be requested on-demand with POST /snapshots.

Public endpoints (no auth):
  GET  /snapshots               – list all snapshots (newest first)
  GET  /snapshots/{id}          – snapshot metadata
  GET  /snapshots/{id}/diff     – field-level diff vs previous snapshot
  GET  /snapshots/{id}/diff/{prev_id} – diff vs a specific earlier snapshot

Protected endpoints (API key required):
  POST /snapshots               – take a snapshot of the current curated state
  DELETE /snapshots/{id}        – remove a snapshot (frees storage)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.auth import require_api_key
from api.schemas import SnapshotCreate, SnapshotOut, SnapshotDiffOut, CaseDiff
from db.models import CuratedSnapshot
from db.session import SyncSessionLocal
from pipeline.snapshot import take_snapshot, diff_snapshots

router = APIRouter(tags=["Snapshots"])


def _get_sync_session() -> Session:
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── Public endpoints ──────────────────────────────────────────────────

@router.get("/snapshots", response_model=list[SnapshotOut])
def list_snapshots(
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(_get_sync_session),
):
    """List all curated snapshots, newest first."""
    rows = (
        session.query(CuratedSnapshot)
        .order_by(CuratedSnapshot.taken_at.desc())
        .limit(limit)
        .all()
    )
    return rows


@router.get("/snapshots/{snap_id}", response_model=SnapshotOut)
def get_snapshot(
    snap_id: int,
    session: Session = Depends(_get_sync_session),
):
    """Get metadata for a single snapshot."""
    snap = session.query(CuratedSnapshot).get(snap_id)
    if snap is None:
        raise HTTPException(404, f"Snapshot {snap_id} not found")
    return snap


@router.get("/snapshots/{snap_id}/diff", response_model=SnapshotDiffOut)
def get_snapshot_diff(
    snap_id: int,
    prev_id: int = Query(None, description="Compare against this specific earlier snapshot ID"),
    session: Session = Depends(_get_sync_session),
):
    """
    Show what changed between snapshot *snap_id* and the previous one.

    Pass ``?prev_id=N`` to compare against any specific earlier snapshot.

    Response fields:
    - ``added_count`` / ``removed_count`` / ``changed_count`` – summary
    - ``cases`` – list of added / removed / changed case records
    - ``changed_fields`` – per-field ``{old, new}`` for changed cases
    """
    try:
        result = diff_snapshots(session, snap_id, prev_id=prev_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))

    # Convert cases list → list[CaseDiff]
    cases = [CaseDiff(**c) for c in result["cases"]]

    return SnapshotDiffOut(
        snapshot_id=result["snapshot_id"],
        snapshot_label=result["snapshot_label"],
        snapshot_taken_at=result["snapshot_taken_at"],
        prev_snapshot_id=result["prev_snapshot_id"],
        prev_snapshot_label=result["prev_snapshot_label"],
        added_count=result["added_count"],
        removed_count=result["removed_count"],
        changed_count=result["changed_count"],
        unchanged_count=result["unchanged_count"],
        cases=cases,
    )


# ── Protected endpoints ───────────────────────────────────────────────

@router.post(
    "/snapshots",
    response_model=SnapshotOut,
    dependencies=[Depends(require_api_key)],
    status_code=201,
)
def create_snapshot(
    body: SnapshotCreate,
    session: Session = Depends(_get_sync_session),
):
    """
    Manually take a snapshot of the current curated state.

    Useful before running a bulk curation edit so you can diff before/after.
    """
    snap = take_snapshot(
        session,
        label=body.label,
        description=body.description,
        is_auto=False,
    )
    session.commit()
    return snap


@router.delete(
    "/snapshots/{snap_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_snapshot(
    snap_id: int,
    session: Session = Depends(_get_sync_session),
):
    """Delete a snapshot and all its frozen case rows (CASCADE)."""
    snap = session.query(CuratedSnapshot).get(snap_id)
    if snap is None:
        raise HTTPException(404, f"Snapshot {snap_id} not found")
    session.delete(snap)
    session.commit()
