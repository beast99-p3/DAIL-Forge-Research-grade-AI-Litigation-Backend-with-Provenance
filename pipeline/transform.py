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

import logging
import re
from datetime import date, datetime
from typing import Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import (
    Case, CaseTag, Docket, Document, SecondarySource, Tag,
    RawDocument, RawSecondarySource,
)

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


def synthesize_stub_cases(session: Session) -> int:
    """
    Create a stub ``Case`` for every Case_Number referenced in the data
    tables that does not already exist in ``cases``.

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
        session.add(Case(
            case_id=str(case_num),
            case_name=f"[Stub] Case #{case_num}",
            is_stub=True,
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


def transform_all(session: Session) -> dict[str, int]:
    """
    Run the full RAW → CURATED transform pipeline.

    Order:
    1. Synthesise stub cases (so FK targets exist)
    2. Transform documents
    3. Transform secondary sources
    """
    return {
        "stub_cases": synthesize_stub_cases(session),
        "documents": transform_documents(session),
        "secondary_sources": transform_secondary_sources(session),
    }
