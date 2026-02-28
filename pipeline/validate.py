"""
Post-load validation checks.

Returns a list of warnings / errors that a human should review.
"""

import logging
from dataclasses import dataclass
from typing import List

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from db.models import (
    Case, Docket, Document, SecondarySource,
    RawCase, RawDocket, RawDocument, RawSecondarySource,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    level: str   # "warning" | "error"
    check: str
    message: str


def validate(session: Session) -> List[ValidationResult]:
    results: List[ValidationResult] = []

    # 1. Duplicate case_id in curated cases
    dupes = (
        session.query(Case.case_id, func.count(Case.id))
        .group_by(Case.case_id)
        .having(func.count(Case.id) > 1)
        .all()
    )
    for case_id, cnt in dupes:
        results.append(ValidationResult(
            "error", "duplicate_case_id",
            f"case_id={case_id!r} appears {cnt} times in curated cases",
        ))

    # 2. Cases without filing_date
    missing_date = session.query(Case).filter(Case.filing_date.is_(None)).count()
    if missing_date:
        results.append(ValidationResult(
            "warning", "missing_filing_date",
            f"{missing_date} curated cases have no filing_date",
        ))

    # 3. Cases without case_name
    missing_name = session.query(Case).filter(Case.case_name.is_(None)).count()
    if missing_name:
        results.append(ValidationResult(
            "warning", "missing_case_name",
            f"{missing_name} curated cases have no case_name",
        ))

    # 4. Orphan raw dockets (case_id not in curated cases)
    orphan_dockets = (
        session.query(RawDocket)
        .filter(~RawDocket.case_id.in_(session.query(Case.case_id)))
        .filter(RawDocket.case_id.isnot(None))
        .count()
    )
    if orphan_dockets:
        results.append(ValidationResult(
            "warning", "orphan_raw_dockets",
            f"{orphan_dockets} raw docket rows reference a case_id not found in curated cases",
        ))

    # 5. Orphan raw documents
    orphan_docs = (
        session.query(RawDocument)
        .filter(~RawDocument.case_id.in_(session.query(Case.case_id)))
        .filter(RawDocument.case_id.isnot(None))
        .count()
    )
    if orphan_docs:
        results.append(ValidationResult(
            "warning", "orphan_raw_documents",
            f"{orphan_docs} raw document rows reference a case_id not found in curated cases",
        ))

    # 6. Orphan raw secondary sources
    orphan_ss = (
        session.query(RawSecondarySource)
        .filter(~RawSecondarySource.case_id.in_(session.query(Case.case_id)))
        .filter(RawSecondarySource.case_id.isnot(None))
        .count()
    )
    if orphan_ss:
        results.append(ValidationResult(
            "warning", "orphan_raw_secondary_sources",
            f"{orphan_ss} raw secondary-source rows reference a case_id not found in curated cases",
        ))

    # 7. Row-count summary
    for label, raw_model, curated_model in [
        ("cases", RawCase, Case),
        ("dockets", RawDocket, Docket),
        ("documents", RawDocument, Document),
        ("secondary_sources", RawSecondarySource, SecondarySource),
    ]:
        raw_ct = session.query(raw_model).count()
        cur_ct = session.query(curated_model).count()
        diff = raw_ct - cur_ct
        if diff > 0:
            results.append(ValidationResult(
                "warning", f"row_count_{label}",
                f"{label}: {raw_ct} raw rows → {cur_ct} curated rows ({diff} dropped/skipped)",
            ))

    # Log results
    for r in results:
        log_fn = logger.error if r.level == "error" else logger.warning
        log_fn("[%s] %s: %s", r.level.upper(), r.check, r.message)

    if not results:
        logger.info("All validation checks passed ✓")

    return results
