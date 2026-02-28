"""
Post-load validation checks  (schema-aware v2).

Severity rules
--------------
ERROR   – Integrity violations that indicate corrupt or unusable data.
          These BLOCK startup unless DAIL_ALLOW_DIRTY_STARTUP=true.
          Examples: orphan FK references, duplicate PKs

WARNING – Data quality issues that are non-blocking but need curator review.
          Examples: missing optional fields, stub-heavy dataset

INFO    – Informational counters (always emitted).
"""

import logging
from dataclasses import dataclass
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import (
    Case, Docket, Document, SecondarySource,
    RawDocument, RawSecondarySource, RawSchemaField,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    level: str   # "warning" | "error"
    check: str
    message: str


def validate(session: Session) -> List[ValidationResult]:
    results: List[ValidationResult] = []

    # 1. Duplicate case_id in curated cases  → ERROR (integrity violation)
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

    # 2. Stub vs real case summary  → INFO (never blocking)
    total_cases = session.query(Case).count()
    stub_cases = session.query(Case).filter(Case.is_stub.is_(True)).count()
    real_cases = total_cases - stub_cases
    results.append(ValidationResult(
        "info",
        "stub_case_summary",
        f"{total_cases} total cases: {real_cases} real, {stub_cases} stubs "
        f"(synthesised from FK references)",
    ))

    # 3. Cases without case_name (stubs are expected to have placeholder names)
    missing_name = session.query(Case).filter(
        Case.case_name.is_(None), Case.is_stub.is_(False)
    ).count()
    if missing_name:
        results.append(ValidationResult(
            "warning", "missing_case_name",
            f"{missing_name} non-stub curated cases have no case_name",
        ))

    # 4. Orphan raw documents → ERROR (every document must link to a case)
    orphan_docs = (
        session.query(RawDocument)
        .filter(~RawDocument.case_id.in_(session.query(Case.case_id)))
        .filter(RawDocument.case_id.isnot(None))
        .count()
    )
    if orphan_docs:
        results.append(ValidationResult(
            "error", "orphan_raw_documents",
            f"{orphan_docs} raw document rows reference a case_id not found in curated cases "
            "(FK integrity violated – these rows were dropped from documents table)",
        ))

    # 5. Orphan raw secondary sources → ERROR
    orphan_ss = (
        session.query(RawSecondarySource)
        .filter(~RawSecondarySource.case_id.in_(session.query(Case.case_id)))
        .filter(RawSecondarySource.case_id.isnot(None))
        .count()
    )
    if orphan_ss:
        results.append(ValidationResult(
            "error", "orphan_raw_secondary_sources",
            f"{orphan_ss} raw secondary-source rows reference a case_id not found in curated cases "
            "(FK integrity violated – these rows were dropped from secondary_sources table)",
        ))

    # 6. Schema-metadata coverage
    schema_count = session.query(RawSchemaField).count()
    schema_files = (
        session.query(RawSchemaField.source_file)
        .distinct()
        .all()
    )
    file_names = [r[0] for r in schema_files]
    results.append(ValidationResult(
        "info" if schema_count > 0 else "warning",
        "schema_metadata",
        f"{schema_count} schema-field definitions loaded from {len(file_names)} file(s): "
        + ", ".join(file_names) if file_names else "No schema files loaded",
    ))

    # 7. Row-count summary for data tables
    for label, raw_model, curated_model in [
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
        if r.level == "error":
            logger.error("[%s] %s: %s", r.level.upper(), r.check, r.message)
        elif r.level == "warning":
            logger.warning("[%s] %s: %s", r.level.upper(), r.check, r.message)
        else:
            logger.info("[%s] %s: %s", r.level.upper(), r.check, r.message)

    if not any(r.level in ("error", "warning") for r in results):
        logger.info("All validation checks passed ✓")

    return results
