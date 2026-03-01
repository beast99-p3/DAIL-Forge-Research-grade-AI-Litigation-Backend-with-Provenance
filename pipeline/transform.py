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
    RawDocument, RawSecondarySource, RawCase, RawDocket,
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


# ── Real case transform ──────────────────────────────────────────────

def transform_cases(session: Session, run_id: Optional[str] = None) -> int:
    """
    Transform real case data from ``raw_case`` → ``cases``.
    Creates full case records with all metadata and tags from Case_Table.xlsx.
    
    Returns the number of cases created.
    """
    # Idempotency: skip if curated cases already exist (non-stubs)
    existing_count = session.query(Case).filter_by(is_stub=False).count()
    if existing_count > 0:
        logger.info("cases table already has %d real cases – skipping transform", existing_count)
        return existing_count

    raws = session.query(RawCase).all()
    if not raws:
        logger.info("No raw_case data found – skipping case transform")
        return 0
    
    count = 0
    for raw in raws:
        # Create the case record
        fingerprint = _compute_fingerprint(raw.case_id, raw.case_name)
        case = Case(
            case_id=raw.case_id or str(raw.id),
            legacy_case_number=raw.case_id,
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
            is_stub=False,
            case_fingerprint=fingerprint,
        )
        session.add(case)
        session.flush()  # Get the case.id for relationships

        # Process tag lists
        for field_name, tag_type in TAG_FIELD_MAP.items():
            raw_value = getattr(raw, field_name, None)
            if raw_value:
                for tag_val in split_multi_select(raw_value):
                    tag = get_or_create_tag(session, tag_type, tag_val)
                    ct = CaseTag(case_id=case.id, tag_id=tag.id)
                    session.add(ct)
        
        # Log creation in change_log if run_id provided
        if run_id:
            log_entry = ChangeLog(
                table_name="cases",
                record_id=case.id,
                field_name="*",
                old_value=None,
                new_value="[case created from raw_case]",
                editor_id="pipeline",
                reason="Case created from raw_case data",
                actor_type="pipeline",
                operation="create",
                run_id=run_id,
                citation_justification="Auto-generated by pipeline from Case_Table export",
            )
            session.add(log_entry)

        count += 1

    session.commit()
    logger.info("Transformed %d real cases from raw_case", count)
    return count


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

        # IMPORTANT: The "court" key in raw_document extra_fields actually
        # contains document descriptions ("Complaint", "Motion to Dismiss"),
        # NOT real court names.  Exclude it from scalar mapping to prevent
        # polluting Case.court with garbage data.
        # Court data should come from CourtListener URL parsing instead.
        _SKIP_EXTRA_SCALARS = {"court"}

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
            if canonical in _SKIP_EXTRA_SCALARS:
                continue  # skip unreliable extra_fields
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


def transform_dockets(session: Session) -> int:
    """
    Transform raw docket rows from ``raw_docket`` → ``dockets``.

    Returns the number of docket entries created.
    """
    # Idempotency: skip if curated dockets already exist
    if session.query(Docket).count() > 0:
        existing = session.query(Docket).count()
        logger.info("dockets table already has %d rows – skipping transform", existing)
        return existing

    raws = session.query(RawDocket).all()
    if not raws:
        logger.info("No raw_docket data found – skipping docket transform")
        return 0

    count = 0
    for raw in raws:
        case_pk = _resolve_case_pk(session, raw.case_id)
        if not case_pk:
            logger.warning(
                "Orphan docket row %d: case_id=%s not found",
                raw.row_number, raw.case_id,
            )
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


def transform_all(session: Session, run_id: Optional[str] = None) -> dict[str, int]:
    """
    Run the full RAW → CURATED transform pipeline.

    Pass *run_id* (from the active PipelineRun) so that every change_log
    entry created during this run is traceable back to the pipeline execution.

    Order:
    1. Transform real case data from raw_case (creates complete case records)
    2. Synthesise stub cases for any missing FKs (so all FK targets exist)
    3. Enrich cases from extra_fields (court, plaintiff, tags, etc.)
    4. Transform documents
    5. Transform secondary sources
    6. Transform dockets
    7. Extract courts from CourtListener URLs
    8. Extract case names from URL slugs and source titles
    """
    return {
        "real_cases": transform_cases(session, run_id=run_id),
        "stub_cases": synthesize_stub_cases(session, run_id=run_id),
        "cases_enriched": enrich_cases_from_raw_documents(session, run_id=run_id),
        "documents": transform_documents(session),
        "secondary_sources": transform_secondary_sources(session),
        "dockets": transform_dockets(session),
        "courts_extracted": extract_courts_from_urls(session),
        "names_extracted": extract_names_from_urls_and_sources(session),
    }


# ── Post-transform enrichment from URLs ─────────────────────────────

# PACER court codes → human-readable names
_COURT_CODE_MAP = {
    "akd": "U.S. District Court, District of Alaska",
    "almd": "U.S. District Court, Middle District of Alabama",
    "alnd": "U.S. District Court, Northern District of Alabama",
    "alsd": "U.S. District Court, Southern District of Alabama",
    "ared": "U.S. District Court, Eastern District of Arkansas",
    "arwd": "U.S. District Court, Western District of Arkansas",
    "azd": "U.S. District Court, District of Arizona",
    "cacd": "U.S. District Court, Central District of California",
    "caed": "U.S. District Court, Eastern District of California",
    "cand": "U.S. District Court, Northern District of California",
    "casd": "U.S. District Court, Southern District of California",
    "cod": "U.S. District Court, District of Colorado",
    "ctd": "U.S. District Court, District of Connecticut",
    "dcd": "U.S. District Court, District of Columbia",
    "ded": "U.S. District Court, District of Delaware",
    "flmd": "U.S. District Court, Middle District of Florida",
    "flnd": "U.S. District Court, Northern District of Florida",
    "flsd": "U.S. District Court, Southern District of Florida",
    "gamd": "U.S. District Court, Middle District of Georgia",
    "gand": "U.S. District Court, Northern District of Georgia",
    "gasd": "U.S. District Court, Southern District of Georgia",
    "hid": "U.S. District Court, District of Hawaii",
    "iasd": "U.S. District Court, Southern District of Iowa",
    "iand": "U.S. District Court, Northern District of Iowa",
    "idd": "U.S. District Court, District of Idaho",
    "ilcd": "U.S. District Court, Central District of Illinois",
    "ilnd": "U.S. District Court, Northern District of Illinois",
    "ilsd": "U.S. District Court, Southern District of Illinois",
    "innd": "U.S. District Court, Northern District of Indiana",
    "insd": "U.S. District Court, Southern District of Indiana",
    "ksd": "U.S. District Court, District of Kansas",
    "kyed": "U.S. District Court, Eastern District of Kentucky",
    "kywd": "U.S. District Court, Western District of Kentucky",
    "laed": "U.S. District Court, Eastern District of Louisiana",
    "lamd": "U.S. District Court, Middle District of Louisiana",
    "lawd": "U.S. District Court, Western District of Louisiana",
    "mad": "U.S. District Court, District of Massachusetts",
    "mdd": "U.S. District Court, District of Maryland",
    "med": "U.S. District Court, District of Maine",
    "mied": "U.S. District Court, Eastern District of Michigan",
    "miwd": "U.S. District Court, Western District of Michigan",
    "mnd": "U.S. District Court, District of Minnesota",
    "moed": "U.S. District Court, Eastern District of Missouri",
    "mowd": "U.S. District Court, Western District of Missouri",
    "msnd": "U.S. District Court, Northern District of Mississippi",
    "mssd": "U.S. District Court, Southern District of Mississippi",
    "mtd": "U.S. District Court, District of Montana",
    "nced": "U.S. District Court, Eastern District of North Carolina",
    "ncmd": "U.S. District Court, Middle District of North Carolina",
    "ncwd": "U.S. District Court, Western District of North Carolina",
    "ndd": "U.S. District Court, District of North Dakota",
    "ned": "U.S. District Court, District of Nebraska",
    "nhd": "U.S. District Court, District of New Hampshire",
    "njd": "U.S. District Court, District of New Jersey",
    "nmd": "U.S. District Court, District of New Mexico",
    "nvd": "U.S. District Court, District of Nevada",
    "nyed": "U.S. District Court, Eastern District of New York",
    "nynd": "U.S. District Court, Northern District of New York",
    "nysd": "U.S. District Court, Southern District of New York",
    "nywd": "U.S. District Court, Western District of New York",
    "ohnd": "U.S. District Court, Northern District of Ohio",
    "ohsd": "U.S. District Court, Southern District of Ohio",
    "oked": "U.S. District Court, Eastern District of Oklahoma",
    "oknd": "U.S. District Court, Northern District of Oklahoma",
    "okwd": "U.S. District Court, Western District of Oklahoma",
    "ord": "U.S. District Court, District of Oregon",
    "paed": "U.S. District Court, Eastern District of Pennsylvania",
    "pamd": "U.S. District Court, Middle District of Pennsylvania",
    "pawd": "U.S. District Court, Western District of Pennsylvania",
    "prd": "U.S. District Court, District of Puerto Rico",
    "rid": "U.S. District Court, District of Rhode Island",
    "scd": "U.S. District Court, District of South Carolina",
    "sdd": "U.S. District Court, District of South Dakota",
    "tned": "U.S. District Court, Eastern District of Tennessee",
    "tnmd": "U.S. District Court, Middle District of Tennessee",
    "tnwd": "U.S. District Court, Western District of Tennessee",
    "txed": "U.S. District Court, Eastern District of Texas",
    "txnd": "U.S. District Court, Northern District of Texas",
    "txsd": "U.S. District Court, Southern District of Texas",
    "txwd": "U.S. District Court, Western District of Texas",
    "utd": "U.S. District Court, District of Utah",
    "vaed": "U.S. District Court, Eastern District of Virginia",
    "vawd": "U.S. District Court, Western District of Virginia",
    "vtd": "U.S. District Court, District of Vermont",
    "waed": "U.S. District Court, Eastern District of Washington",
    "wawd": "U.S. District Court, Western District of Washington",
    "wied": "U.S. District Court, Eastern District of Wisconsin",
    "wiwd": "U.S. District Court, Western District of Wisconsin",
    "wvnd": "U.S. District Court, Northern District of West Virginia",
    "wvsd": "U.S. District Court, Southern District of West Virginia",
    "wyd": "U.S. District Court, District of Wyoming",
    "ca1": "U.S. Court of Appeals, First Circuit",
    "ca2": "U.S. Court of Appeals, Second Circuit",
    "ca3": "U.S. Court of Appeals, Third Circuit",
    "ca4": "U.S. Court of Appeals, Fourth Circuit",
    "ca5": "U.S. Court of Appeals, Fifth Circuit",
    "ca6": "U.S. Court of Appeals, Sixth Circuit",
    "ca7": "U.S. Court of Appeals, Seventh Circuit",
    "ca8": "U.S. Court of Appeals, Eighth Circuit",
    "ca9": "U.S. Court of Appeals, Ninth Circuit",
    "ca10": "U.S. Court of Appeals, Tenth Circuit",
    "ca11": "U.S. Court of Appeals, Eleventh Circuit",
    "cadc": "U.S. Court of Appeals, D.C. Circuit",
    "cafc": "U.S. Court of Appeals, Federal Circuit",
}

_VALID_COURT_RE = re.compile(
    r"(district\s+court|circuit\s+court|court\s+of\s+appeals|supreme\s+court"
    r"|superior\s+court|county\s+court|bankruptcy\s+court|federal\s+court"
    r"|court\s+of\s+claims|court\s+of\s+common\s+pleas"
    r"|[NSEWMC]\.?D\.?\s+\w)",
    re.IGNORECASE,
)


def extract_courts_from_urls(session: Session) -> int:
    """
    Extract real court names from CourtListener URLs in documents and
    secondary sources.  Also clears garbage court values (document
    descriptions that leaked via extra_fields mapping).

    Runs after documents/sources are created so URL data is available.
    """
    cases = session.query(Case).filter(Case.court.is_(None)).all()
    if not cases:
        logger.info("All cases already have courts – skipping URL extraction")
        return 0

    enriched = 0
    for case in cases:
        # Collect all URLs for this case
        urls = [d.url for d in case.documents if d.url] + \
               [s.url for s in case.secondary_sources if s.url]

        for url in urls:
            m = re.search(r"gov\.uscourts\.(\w+)\.", url)
            if m:
                code = m.group(1)
                if code in _COURT_CODE_MAP:
                    case.court = _COURT_CODE_MAP[code]
                    enriched += 1
                    break

    session.commit()
    logger.info("Extracted courts from URLs for %d cases", enriched)
    return enriched


def extract_names_from_urls_and_sources(session: Session) -> int:
    """
    Extract proper case names from CourtListener URL slugs and secondary
    source titles for cases that still have generic placeholder names.
    """
    cases = session.query(Case).filter(
        (Case.case_name.like("[Stub]%")) | (Case.case_name.like("AI Litigation Case%"))
    ).all()
    if not cases:
        logger.info("No generic-named cases – skipping name extraction")
        return 0

    enriched = 0
    for case in cases:
        urls = [d.url for d in case.documents if d.url] + \
               [s.url for s in case.secondary_sources if s.url]

        new_name = None

        # Strategy 1: CourtListener docket/opinion URL slugs
        for url in urls:
            m = re.search(r"/(docket|opinion)/\d+(?:/\d+)?/([\w-]+)/?", url)
            if not m:
                continue
            slug = m.group(2)
            parts = slug.split("-")
            if len(parts) >= 3 and parts[0] == "in" and parts[1] == "re":
                new_name = "In re " + " ".join(p.capitalize() for p in parts[2:])
                break
            if "v" in parts:
                v_i = parts.index("v")
                if v_i > 0 and v_i < len(parts) - 1:
                    p1 = " ".join(p.capitalize() for p in parts[:v_i])
                    p2 = " ".join(p.capitalize() for p in parts[v_i+1:])
                    new_name = f"{p1} v. {p2}"
                    break

        # Strategy 2: Secondary source titles with "v." patterns
        if not new_name:
            for ss in case.secondary_sources:
                t = ss.source_title or ""
                m = re.search(
                    r"([A-Z][A-Za-z\s.\'&,()\-]+?)\s+(?:v\.?s?\.?)\s+([A-Z][A-Za-z\s.\'&,()\-]+)",
                    t,
                )
                if m:
                    new_name = f"{m.group(1).strip()} v. {m.group(2).strip()}"
                    break

        # Strategy 3: Use first informative source title
        if not new_name:
            for ss in case.secondary_sources:
                t = (ss.source_title or "").strip()
                if t and len(t) > 15 and not t.startswith("http"):
                    new_name = t[:120] if len(t) > 120 else t
                    break

        if new_name:
            case.case_name = new_name
            enriched += 1

    session.commit()
    logger.info("Extracted names for %d cases", enriched)
    return enriched
