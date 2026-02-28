"""
RAW → CURATED transform  (schema-aware v2).

Key change from v1
------------------
Case_Table and Docket_Table are *schema metadata*, not data.  There are
**no raw case rows** to transform.  Instead we:

1. Collect every unique ``Case_Number`` referenced in ``raw_document``
   and ``raw_secondary_source``.
2. Synthesise one *stub* ``Case`` record per unique number
   (``is_stub = True``).
3. Transform documents and secondary sources as before, now with valid
   FK targets.

When a real case-data export becomes available the pipeline can be
extended to merge real records in, clearing ``is_stub``.
"""

import hashlib
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import (
    Case, CaseTag, ChangeLog, Docket, Document, SecondarySource, Tag,
    RawDocument, RawSecondarySource,
)
from pipeline.column_map import CASE_ALIASES, build_column_map

logger = logging.getLogger(__name__)

# ── Date parsing ─────────────────────────────────────────────────────

DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
]


def parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    val = val.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    # Try dateutil fallback
    try:
        from dateutil.parser import parse as du_parse
        return du_parse(val).date()
    except Exception:
        logger.debug("Could not parse date: %r", val)
        return None


# ── Tag helpers (retained for future use when real case data arrives) ─

def split_multi_select(val: Optional[str]) -> list[str]:
    """Split a delimited multi-select field into individual tag values."""
    if not val:
        return []
    parts = re.split(r"[;|,\n]+", val)
    return [p.strip() for p in parts if p.strip()]


def get_or_create_tag(session: Session, tag_type: str, value: str) -> Tag:
    """Return existing Tag or create a new one."""
    tag = session.query(Tag).filter_by(tag_type=tag_type, value=value).first()
    if not tag:
        tag = Tag(tag_type=tag_type, value=value)
        session.add(tag)
        session.flush()
    return tag


TAG_FIELD_MAP = {
    "issue_list": "issue",
    "area_list": "area",
    "cause_list": "cause",
    "algorithm_list": "algorithm",
    "harm_list": "harm",
}

def _compute_fingerprint(*parts: Optional[str]) -> str:
    """
    SHA-256 fingerprint of the concatenated best-known identifiers.
    Used to enable safe merge/de-dup of case records across pipeline runs.
    """
    key = "|".join(p.strip().lower() if p else "" for p in parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]

# ── Stub case synthesis ──────────────────────────────────────────────

def _collect_case_numbers(session: Session) -> Set[str]:
    """
    Gather every unique ``case_id`` value referenced in data raw tables.
    These are the Case_Number values from Document_Table and
    Secondary_Source_Coverage_Table.
    """
    ids: Set[str] = set()

    for model in (RawDocument, RawSecondarySource):
        rows = (
            session.query(model.case_id)
            .filter(model.case_id.isnot(None))
            .distinct()
            .all()
        )
        ids.update(r[0] for r in rows)

    return ids


def synthesize_stub_cases(session: Session, run_id: Optional[str] = None) -> int:
    """
    Create a stub ``Case`` for every Case_Number referenced in the data
    tables that does not already exist in ``cases``.

    - ``legacy_case_number`` stores the original surrogate key from the export.
    - ``case_fingerprint`` is seeded from the legacy number until real data
      is promoted via POST /cases/{id}/promote.
    - Every new stub creation is logged in ``change_log`` with
      ``actor_type='pipeline'`` so bulk loads don’t pollute human edits.

    Returns the number of stubs created.
    """
    needed = _collect_case_numbers(session)
    if not needed:
        logger.info("No case numbers found in data tables – nothing to synthesise")
        return 0

    existing = {
        r[0]
        for r in session.query(Case.case_id).filter(Case.case_id.in_(needed)).all()
    }
    to_create = needed - existing

    logger.info(
        "Stub synthesis: %d unique case numbers referenced, %d already exist, %d to create",
        len(needed), len(existing), len(to_create),
    )

    count = 0
    for case_num in sorted(to_create):
        fingerprint = _compute_fingerprint(str(case_num))
        case = Case(
            case_id=str(case_num),
            legacy_case_number=str(case_num),
            case_name=f"[Stub] Case #{case_num}",
            is_stub=True,
            case_fingerprint=fingerprint,
        )
        session.add(case)
        session.flush()  # get PK
        session.add(ChangeLog(
            table_name="cases",
            record_id=case.id,
            field_name="is_stub",
            old_value=None,
            new_value="true",
            editor_id="pipeline",
            reason="Stub synthesised from FK reference in data tables",
            actor_type="pipeline",
            operation="create",
            run_id=run_id,
            citation_justification="Auto-generated by pipeline; no curator source available",
        ))
        count += 1

    session.commit()
    logger.info("Synthesised %d stub case records", count)
    return count


# ── FK resolver ──────────────────────────────────────────────────────

def _resolve_case_pk(session: Session, raw_case_id: Optional[str]) -> Optional[int]:
    """Look up curated ``cases.id`` from a raw ``case_id`` string."""
    if not raw_case_id:
        return None
    case = session.query(Case).filter_by(case_id=raw_case_id).first()
    return case.id if case else None


# ── Case enrichment from extra_fields ───────────────────────────────

_TAG_CANONICAL = {"issue_list", "area_list", "cause_list", "algorithm_list", "harm_list"}
_TAG_TYPE_MAP = {
    "issue_list": "issue",
    "area_list": "area",
    "cause_list": "cause",
    "algorithm_list": "algorithm",
    "harm_list": "harm",
}
_CASE_SCALARS = {
    "case_name", "court", "case_status", "case_outcome",
    "case_type", "plaintiff", "defendant", "judge", "summary",
}
_CASE_DATES = {"filing_date", "closing_date"}


def _get_or_create_tag(session: Session, tag_type: str, value: str) -> Tag:
    tag = session.query(Tag).filter_by(tag_type=tag_type, value=value).first()
    if not tag:
        slug = value.lower().strip().replace(" ", "_")[:120]
        tag = Tag(
            tag_type=tag_type, value=value, slug=slug,
            is_official=True, source="pipeline",
        )
        session.add(tag)
        session.flush()
    return tag


def enrich_cases_from_raw_documents(
    session: Session, run_id: Optional[str] = None
) -> int:
    """
    Enrich stub Case records with case-level fields stored in
    ``raw_document.extra_fields``.

    The Document_Table export contains many columns beyond the five
    mapped by DOCUMENT_ALIASES (court, plaintiff, case name, status,
    tags, etc.).  Those columns land in ``extra_fields`` as JSON.
    This step fuzzy-matches those keys against CASE_ALIASES and writes
    the values back into the Case rows.

    Also creates Tag / CaseTag rows for multi-value fields (issue_list,
    area_list, cause_list, algorithm_list, harm_list).

    Idempotent: skips cases that already have a court value (already enriched).
    Returns the number of cases updated.
    """
    stubs = session.query(Case).all()
    if not stubs:
        logger.info("No cases to enrich")
        return 0

    enriched = 0
    for case in stubs:
        # Skip if already enriched (court is the most reliable indicator)
        if case.court is not None:
            continue

        # Aggregate extra_fields across all raw doc rows for this case
        # (first non-null value wins for each key)
        raw_docs = (
            session.query(RawDocument)
            .filter(RawDocument.case_id == case.case_id)
            .order_by(RawDocument.row_number)
            .all()
        )
        if not raw_docs:
            continue

        merged: Dict[str, str] = {}
        for raw in raw_docs:
            ef = raw.extra_fields or {}
            for k, v in ef.items():
                if k not in merged and v and str(v).strip():
                    merged[k] = str(v).strip()

        if not merged:
            continue

        # Fuzzy-map extra_fields keys → canonical CASE_ALIASES names
        col_map = build_column_map(list(merged.keys()), CASE_ALIASES)

        changed_fields: Dict[str, Any] = {}
        tag_fields: Dict[str, str] = {}

        for raw_col, canonical in col_map.items():
            val = merged.get(raw_col)
            if not val:
                continue
            if canonical == "case_id":
                continue  # never overwrite PK
            if canonical in _TAG_CANONICAL:
                tag_fields[canonical] = val
                continue
            if canonical in _CASE_DATES:
                parsed = parse_date(val)
                if parsed and getattr(case, canonical) is None:
                    setattr(case, canonical, parsed)
                    changed_fields[canonical] = str(parsed)
            elif canonical in _CASE_SCALARS:
                current = getattr(case, canonical)
                # Replace placeholder stub name with real caption
                if current is None or (canonical == "case_name" and str(current).startswith("[Stub]")):
                    setattr(case, canonical, val)
                    changed_fields[canonical] = val

        # Create tags for multi-value fields
        for canonical, raw_val in tag_fields.items():
            tag_type = _TAG_TYPE_MAP[canonical]
            for tag_value in split_multi_select(raw_val):
                tag = _get_or_create_tag(session, tag_type, tag_value)
                exists = (
                    session.query(CaseTag)
                    .filter_by(case_id=case.id, tag_id=tag.id)
                    .first()
                )
                if not exists:
                    session.add(CaseTag(case_id=case.id, tag_id=tag.id))

        if changed_fields or tag_fields:
            # Recompute fingerprint with real identifiers now available
            case.case_fingerprint = _compute_fingerprint(
                case.case_name or "",
                case.court or "",
                str(case.filing_date) if case.filing_date else "",
            )
            if changed_fields:
                session.add(ChangeLog(
                    table_name="cases",
                    record_id=case.id,
                    field_name="_bulk_enrich",
                    old_value=None,
                    new_value=str(list(changed_fields.keys())),
                    editor_id="pipeline",
                    reason="Case enriched from extra_fields in raw_document rows",
                    actor_type="pipeline",
                    operation="update",
                    run_id=run_id,
                    citation_justification="Auto-enriched from Document_Table export",
                ))
            enriched += 1

    session.commit()
    logger.info("Enriched %d cases from raw_document extra_fields", enriched)
    return enriched


# ── Transform functions ──────────────────────────────────────────────

def transform_documents(session: Session) -> int:
    # Idempotency: skip if curated documents already exist
    if session.query(Document).count() > 0:
        existing = session.query(Document).count()
        logger.info("documents table already has %d rows – skipping transform", existing)
        return existing

    raws = session.query(RawDocument).all()
    count = 0
    for raw in raws:
        case_pk = _resolve_case_pk(session, raw.case_id)
        if not case_pk:
            logger.warning("Orphan document row %d: case_id=%s not found", raw.row_number, raw.case_id)
            continue
        session.add(Document(
            case_id=case_pk,
            document_title=raw.document_title,
            document_type=raw.document_type,
            document_date=parse_date(raw.document_date),
            url=raw.url,
        ))
        count += 1
    session.commit()
    logger.info("Transformed %d documents", count)
    return count


def transform_secondary_sources(session: Session) -> int:
    # Idempotency: skip if curated sources already exist
    if session.query(SecondarySource).count() > 0:
        existing = session.query(SecondarySource).count()
        logger.info("secondary_sources table already has %d rows – skipping transform", existing)
        return existing

    raws = session.query(RawSecondarySource).all()
    count = 0
    for raw in raws:
        case_pk = _resolve_case_pk(session, raw.case_id)
        if not case_pk:
            logger.warning("Orphan secondary source row %d: case_id=%s not found", raw.row_number, raw.case_id)
            continue
        session.add(SecondarySource(
            case_id=case_pk,
            source_title=raw.source_title,
            source_type=raw.source_type,
            publication_date=parse_date(raw.publication_date),
            author=raw.author,
            url=raw.url,
        ))
        count += 1
    session.commit()
    logger.info("Transformed %d secondary sources", count)
    return count


def transform_all(session: Session, run_id: Optional[str] = None) -> dict[str, int]:
    """
    Run the full RAW → CURATED transform pipeline.

    Pass *run_id* (from the active PipelineRun) so that every change_log
    entry created during this run is traceable back to the pipeline execution.

    Order:
    1. Synthesise stub cases (so FK targets exist)
    2. Enrich cases from extra_fields (court, plaintiff, tags, etc.)
    3. Transform documents
    4. Transform secondary sources
    """
    return {
        "stub_cases": synthesize_stub_cases(session, run_id=run_id),
        "cases_enriched": enrich_cases_from_raw_documents(session, run_id=run_id),
        "documents": transform_documents(session),
        "secondary_sources": transform_secondary_sources(session),
    }
