"""
Incremental / Delta Loader for Excel → RAW tables.

Instead of the original "skip entire file if any rows exist" approach,
this module performs a true *per-row delta load*:

  1. Compute a SHA-256 checksum of every incoming row's field values.
  2. Look up the existing RAW row by its natural key:
       - RawCase         →  ``case_id``  (or ``(source_file, row_number)`` fallback)
       - All others      →  ``(source_file, row_number)``
  3. Compare checksums:
       - Row is NEW      →  INSERT  (action='insert')
       - Checksum differs →  UPDATE fields + log changed fields  (action='update')
       - Checksum matches →  no DB write  (action='skip')
  4. Write one ``RawDeltaLog`` row per Excel row processed.

This gives complete per-row provenance: every change in the source data
produces a traceable audit trail before the curated layer is updated.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import pandas as pd
from sqlalchemy.orm import Session

from db.models import (
    RawCase, RawDocument, RawSecondarySource, RawSchemaField, RawDocket,
    RawDeltaLog,
)
from pipeline.column_map import (
    DOCUMENT_ALIASES, SECONDARY_SOURCE_ALIASES,
    SCHEMA_FIELD_ALIASES, CASE_ALIASES, DOCKET_ALIASES,
    build_column_map, is_schema_metadata_file,
)

# Re-export so callers can import from one place
from pipeline.excel_loader import (   # noqa: F401
    DATA_DIR, SCHEMA_FILE_CONFIG, DATA_FILE_CONFIG,
    compute_file_hashes, detect_schema_drift, _safe_str,
)

logger = logging.getLogger(__name__)

# Fields that are system-managed and must NOT be included in the checksum
_SYSTEM_FIELDS = frozenset({"id", "loaded_at", "row_checksum"})

# RAW_DATA_FIELDS lists all content fields per model (in insertion order)
# used to compute the canonical JSON for hashing.
def _content_fields(kwargs: dict) -> dict:
    """Return only the user-data fields from a kwargs dict."""
    return {k: v for k, v in kwargs.items() if k not in _SYSTEM_FIELDS}


def _row_checksum(data: dict) -> str:
    """
    Return a stable 64-hex SHA-256 digest of *data*.

    Values are normalised to string so that None and '' are distinct but
    0.0 and '0.0' are treated equivalently (acceptable for drift detection).
    """
    canon = json.dumps(
        {k: (str(v) if v is not None else None) for k, v in sorted(data.items())},
        ensure_ascii=False,
    )
    return hashlib.sha256(canon.encode()).hexdigest()


def _fields_changed(old_obj: Any, new_kwargs: dict) -> dict:
    """
    Return {field: {old, new}} for every field where the value changed.
    Only content fields (not system fields) are compared.
    """
    changed: dict = {}
    for field, new_val in new_kwargs.items():
        if field in _SYSTEM_FIELDS:
            continue
        old_val = getattr(old_obj, field, None)
        if str(old_val) != str(new_val):
            changed[field] = {"old": str(old_val), "new": str(new_val)}
    return changed


def load_schema_to_raw_delta(
    session: Session,
    filepath: Path,
    run_id: str,
    sheet_name: str | int = 1,
) -> dict:
    """Delta-load the schema-metadata sheet of an Excel file into ``raw_schema_field``."""
    logger.info("[delta] %s (sheet=%r) → raw_schema_field", filepath.name, sheet_name)

    try:
        df = pd.read_excel(filepath, sheet_name=sheet_name, engine="openpyxl")
    except Exception as exc:
        logger.warning("  Could not read sheet %r from %s: %s", sheet_name, filepath.name, exc)
        return {"insert": 0, "update": 0, "skip": 0}
    headers = list(df.columns)
    from pipeline.column_map import build_column_map
    col_map = build_column_map(headers, SCHEMA_FIELD_ALIASES)
    extra_cols = [h for h in headers if h not in set(col_map.keys())]

    counts = {"insert": 0, "update": 0, "skip": 0}
    delta_entries: List[RawDeltaLog] = []

    for idx, row in df.iterrows():
        row_num = int(idx) + 1
        kwargs: Dict[str, Any] = {"source_file": filepath.name, "row_number": row_num}
        for excel_col, canonical in col_map.items():
            kwargs[canonical] = _safe_str(row.get(excel_col))
        if extra_cols:
            extras = {ec: _safe_str(row.get(ec)) for ec in extra_cols if _safe_str(row.get(ec)) is not None}
            kwargs["extra_fields"] = extras or None

        new_check = _row_checksum(_content_fields(kwargs))

        existing = (
            session.query(RawSchemaField)
            .filter(
                RawSchemaField.source_file == filepath.name,
                RawSchemaField.row_number == row_num,
            )
            .first()
        )

        if existing is None:
            obj = RawSchemaField(**kwargs, row_checksum=new_check)
            session.add(obj)
            session.flush()
            action, old_check, changed_fields = "insert", None, None
            row_id = obj.id
            counts["insert"] += 1
        elif existing.row_checksum == new_check:
            action, old_check, changed_fields, row_id = "skip", new_check, None, existing.id
            counts["skip"] += 1
        else:
            changed_fields = _fields_changed(existing, kwargs)
            for k, v in kwargs.items():
                setattr(existing, k, v)
            existing.row_checksum = new_check
            action, old_check, row_id = "update", existing.row_checksum, existing.id
            counts["update"] += 1

        delta_entries.append(RawDeltaLog(
            run_id=run_id, source_file=filepath.name,
            table_name="raw_schema_field", row_number=row_num,
            raw_row_id=row_id, action=action,
            checksum_old=old_check, checksum_new=new_check,
            changed_fields=changed_fields,
        ))

    session.bulk_save_objects(delta_entries)
    session.commit()
    logger.info("  [delta] raw_schema_field: %s", counts)
    return counts


def load_excel_to_raw_delta(
    session: Session,
    filepath: Path,
    model_class: Type,
    aliases: Dict[str, list],
    run_id: str,
    sheet_name: str | int = 0,
) -> dict:
    """
    Delta-load a single data Excel file (sheet 0 by default) into a RAW table.

    Returns ``{"insert": n, "update": n, "skip": n}``.
    """
    logger.info("[delta] %s (sheet=%r) → %s", filepath.name, sheet_name, model_class.__tablename__)

    df = pd.read_excel(filepath, sheet_name=sheet_name, engine="openpyxl")
    headers = list(df.columns)

    if is_schema_metadata_file(headers):
        logger.warning(
            "  ⚠ %s looks like a schema file but configured as data – loading anyway.",
            filepath.name,
        )

    col_map = build_column_map(headers, aliases)
    extra_cols = [h for h in headers if h not in set(col_map.keys())]

    counts = {"insert": 0, "update": 0, "skip": 0}
    delta_entries: List[RawDeltaLog] = []

    # Pre-load existing rows keyed by (source_file, row_number) for speed
    # (avoid one query per row for large files)
    existing_by_rownum: dict = {}
    for obj in (
        session.query(model_class)
        .filter(getattr(model_class, "row_number").isnot(None))
        .all()
    ):
        existing_by_rownum[obj.row_number] = obj

    # For RawCase we also want a case_id → obj index for key updates
    existing_by_case_id: dict = {}
    if model_class is RawCase:
        for obj in existing_by_rownum.values():
            if obj.case_id:
                existing_by_case_id[obj.case_id] = obj

    for idx, row in df.iterrows():
        row_num = int(idx) + 1
        kwargs: Dict[str, Any] = {"row_number": row_num}
        # source_file column (present on RawDocket; absent on other RAW models)
        if hasattr(model_class, "source_file"):
            kwargs["source_file"] = filepath.name
        for excel_col, canonical in col_map.items():
            kwargs[canonical] = _safe_str(row.get(excel_col))
        if extra_cols:
            extras = {ec: _safe_str(row.get(ec)) for ec in extra_cols if _safe_str(row.get(ec)) is not None}
            kwargs["extra_fields"] = extras or None

        new_check = _row_checksum(_content_fields(kwargs))

        # Natural-key lookup for RawCase
        existing: Optional[Any] = None
        if model_class is RawCase and kwargs.get("case_id"):
            existing = existing_by_case_id.get(kwargs["case_id"])
        if existing is None:
            existing = existing_by_rownum.get(row_num)

        if existing is None:
            obj = model_class(**kwargs, row_checksum=new_check)
            session.add(obj)
            session.flush()
            action, old_check, changed_fields = "insert", None, None
            row_id = obj.id
            counts["insert"] += 1
        elif existing.row_checksum == new_check:
            action, old_check, changed_fields, row_id = "skip", new_check, None, existing.id
            counts["skip"] += 1
        else:
            old_check = existing.row_checksum
            changed_fields = _fields_changed(existing, kwargs)
            for k, v in kwargs.items():
                setattr(existing, k, v)
            existing.row_checksum = new_check
            action, row_id = "update", existing.id
            counts["update"] += 1

        delta_entries.append(RawDeltaLog(
            run_id=run_id, source_file=filepath.name,
            table_name=model_class.__tablename__, row_number=row_num,
            raw_row_id=row_id, action=action,
            checksum_old=old_check, checksum_new=new_check,
            changed_fields=changed_fields if action == "update" else None,
        ))

    # Bulk-insert the delta log for this file
    session.bulk_save_objects(delta_entries)
    session.commit()
    logger.info("  [delta] %s: %s", model_class.__tablename__, counts)
    return counts


def load_all_raw_delta(
    session: Session,
    run_id: str,
    data_dir: Path = DATA_DIR,
) -> Dict[str, Any]:
    """
    Delta-load every recognised Excel file from *data_dir*.

    Returns a nested dict:
    ``{filename: {"insert": n, "update": n, "skip": n}}``
    """
    results: Dict[str, Any] = {}

    # Schema files
    for cfg in SCHEMA_FILE_CONFIG:
        matches = sorted(data_dir.glob(cfg["glob"]))
        if not matches:
            logger.warning("No schema file matching %s in %s", cfg["glob"], data_dir)
            continue
        fpath = matches[-1]
        results[f"{fpath.name} (schema)"] = load_schema_to_raw_delta(
            session, fpath, run_id, sheet_name=cfg["sheet"]
        )

    # Data files
    for cfg in DATA_FILE_CONFIG:
        matches = sorted(data_dir.glob(cfg["glob"]))
        if not matches:
            logger.warning("No data file matching %s in %s", cfg["glob"], data_dir)
            continue
        fpath = matches[-1]
        results[fpath.name] = load_excel_to_raw_delta(
            session, fpath, cfg["model"], cfg["aliases"], run_id,
            sheet_name=cfg["sheet"]
        )

    return results
