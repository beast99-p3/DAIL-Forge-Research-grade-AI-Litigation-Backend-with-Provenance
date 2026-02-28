"""
RAW → CURATED transform.

Reads raw_* tables, parses dates, normalises tags, and populates
the curated tables (cases, dockets, documents, secondary_sources, tags, case_tags).
"""

import logging
import re
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import (
    Case, CaseTag, Docket, Document, SecondarySource, Tag,
    RawCase, RawDocket, RawDocument, RawSecondarySource,
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
    # Try pandas-style
    try:
        from dateutil.parser import parse as du_parse
        return du_parse(val).date()
    except Exception:
        logger.debug("Could not parse date: %r", val)
        return None


# ── Tag parsing ──────────────────────────────────────────────────────

def split_multi_select(val: Optional[str]) -> list[str]:
    """Split a delimited multi-select field into individual tag values."""
    if not val:
        return []
    # Common delimiters: comma, semicolon, pipe, newline
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


# ── Transform functions ──────────────────────────────────────────────

TAG_FIELD_MAP = {
    "issue_list": "issue",
    "area_list": "area",
    "cause_list": "cause",
    "algorithm_list": "algorithm",
    "harm_list": "harm",
}


def transform_cases(session: Session) -> int:
    """Transform raw_case → cases + tags + case_tags."""
    raws = session.query(RawCase).all()
    count = 0

    for raw in raws:
        if not raw.case_id:
            logger.warning("Skipping raw_case row %d: no case_id", raw.row_number)
            continue

        # Upsert: skip if already exists
        existing = session.query(Case).filter_by(case_id=raw.case_id).first()
        if existing:
            logger.debug("Case %s already exists, skipping", raw.case_id)
            continue

        case = Case(
            case_id=raw.case_id,
            case_name=raw.case_name,
            court=raw.court,
            filing_date=parse_date(raw.filing_date),
            closing_date=parse_date(raw.closing_date),
            case_status=raw.case_status,
            case_outcome=raw.case_outcome,
            case_type=raw.case_type,
            plaintiff=raw.plaintiff,
            defendant=raw.defendant,
            judge=raw.judge,
            summary=raw.summary,
        )
        session.add(case)
        session.flush()  # need case.id

        # Parse multi-select tag fields
        for raw_field, tag_type in TAG_FIELD_MAP.items():
            raw_value = getattr(raw, raw_field, None)
            for tag_val in split_multi_select(raw_value):
                tag = get_or_create_tag(session, tag_type, tag_val)
                # Check for duplicate link
                exists = session.query(CaseTag).filter_by(
                    case_id=case.id, tag_id=tag.id
                ).first()
                if not exists:
                    session.add(CaseTag(case_id=case.id, tag_id=tag.id))

        count += 1

    session.commit()
    logger.info("Transformed %d cases", count)
    return count


def _resolve_case_pk(session: Session, raw_case_id: Optional[str]) -> Optional[int]:
    """Look up curated cases.id from a raw case_id string."""
    if not raw_case_id:
        return None
    case = session.query(Case).filter_by(case_id=raw_case_id).first()
    return case.id if case else None


def transform_dockets(session: Session) -> int:
    raws = session.query(RawDocket).all()
    count = 0
    for raw in raws:
        case_pk = _resolve_case_pk(session, raw.case_id)
        if not case_pk:
            logger.warning("Orphan docket row %d: case_id=%s not found", raw.row_number, raw.case_id)
            continue
        session.add(Docket(
            case_id=case_pk,
            docket_number=raw.docket_number,
            entry_date=parse_date(raw.entry_date),
            entry_text=raw.entry_text,
            filed_by=raw.filed_by,
        ))
        count += 1
    session.commit()
    logger.info("Transformed %d dockets", count)
    return count


def transform_documents(session: Session) -> int:
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
    """Run the full RAW → CURATED transform pipeline."""
    return {
        "cases": transform_cases(session),
        "dockets": transform_dockets(session),
        "documents": transform_documents(session),
        "secondary_sources": transform_secondary_sources(session),
    }
