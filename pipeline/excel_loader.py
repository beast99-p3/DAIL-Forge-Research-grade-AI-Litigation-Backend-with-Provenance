"""
Excel → RAW table loader  (schema-aware v2).

Reads an Excel workbook, auto-detects whether it is a *schema metadata*
file (column-definition rows like Case_Table / Docket_Table) or a *data*
file (Document_Table / Secondary_Source_Coverage_Table).

Schema files → ``raw_schema_field``
Data files   → the appropriate ``raw_*`` table via fuzzy column mapping.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple, Type

import pandas as pd
from sqlalchemy.orm import Session

from db.models import RawDocument, RawSecondarySource, RawSchemaField, RawCase, RawDocket
from pipeline.column_map import (
    DOCUMENT_ALIASES, SECONDARY_SOURCE_ALIASES, SCHEMA_FIELD_ALIASES,
    CASE_ALIASES, DOCKET_ALIASES,
    build_column_map, is_schema_metadata_file,
)

logger = logging.getLogger(__name__)


def _safe_str(val: Any) -> str | None:
    """Convert a cell value to string, handling NaN/None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val).strip() or None


# ── Schema-metadata loader ───────────────────────────────────────────

def load_schema_to_raw(
    session: Session,
    filepath: Path,
    sheet_name: str | int = 1,
) -> int:
    """
    Load the schema-metadata sheet of an Excel file into ``raw_schema_field``.

    Each file has TWO sheets:
      - Sheet 0: actual data   (loaded by load_excel_to_raw)
      - Sheet 1: column definitions (Name, DataType, Unique, Label) → this function

    Existing rows for this source_file are deleted and reloaded on every
    run so schema changes are always picked up.

    Returns the number of rows inserted.
    """
    logger.info("Loading schema metadata: %s (sheet=%r) → raw_schema_field", filepath.name, sheet_name)

    try:
        df = pd.read_excel(filepath, sheet_name=sheet_name, engine="openpyxl")
    except Exception as exc:
        logger.warning("  Could not read sheet %r from %s: %s", sheet_name, filepath.name, exc)
        return 0

    headers = list(df.columns)
    col_map = build_column_map(headers, SCHEMA_FIELD_ALIASES)

    mapped_cols = set(col_map.keys())
    extra_cols = [h for h in headers if h not in mapped_cols]

    logger.info("  Mapped columns : %s", {v: k for k, v in col_map.items()})

    # Always delete + reload so stale/incorrect rows are corrected
    deleted = (
        session.query(RawSchemaField)
        .filter(RawSchemaField.source_file == filepath.name)
        .delete()
    )
    if deleted:
        logger.info("  Cleared %d existing rows for %s", deleted, filepath.name)
    session.flush()

    rows_inserted = 0
    for idx, row in df.iterrows():
        kwargs: Dict[str, Any] = {
            "source_file": filepath.name,
            "row_number": int(idx) + 1,
        }

        for excel_col, canonical in col_map.items():
            kwargs[canonical] = _safe_str(row.get(excel_col))

        if extra_cols:
            extras = {}
            for ec in extra_cols:
                val = _safe_str(row.get(ec))
                if val is not None:
                    extras[ec] = val
            kwargs["extra_fields"] = extras if extras else None

        session.add(RawSchemaField(**kwargs))
        rows_inserted += 1

    session.commit()
    logger.info("  Inserted %d schema-field rows from %s", rows_inserted, filepath.name)
    return rows_inserted


# ── Data loader ──────────────────────────────────────────────────────

def load_excel_to_raw(
    session: Session,
    filepath: Path,
    model_class: Type,
    aliases: Dict[str, list[str]],
    sheet_name: str | int = 0,
) -> int:
    """
    Load a single data Excel file (sheet 0 by default) into a RAW table.

    Returns the number of rows inserted.
    """
    logger.info("Loading %s (sheet=%r) → %s", filepath.name, sheet_name, model_class.__tablename__)

    df = pd.read_excel(filepath, sheet_name=sheet_name, engine="openpyxl")
    headers = list(df.columns)

    # Safety check — if this looks like a schema file, warn but proceed
    if is_schema_metadata_file(headers):
        logger.warning(
            "  ⚠ %s looks like a schema-metadata file, but it was "
            "configured as data.  Loading anyway.", filepath.name
        )

    col_map = build_column_map(headers, aliases)

    mapped_cols = set(col_map.keys())
    extra_cols = [h for h in headers if h not in mapped_cols]

    logger.info("  Mapped columns : %s", {v: k for k, v in col_map.items()})
    if extra_cols:
        logger.info("  Extra columns  : %s", extra_cols)

    # Idempotency: skip if rows already exist for this model
    existing = session.query(model_class).count()
    if existing > 0:
        logger.info(
            "  Table %s already has %d rows – skipping %s",
            model_class.__tablename__, existing, filepath.name,
        )
        return existing

    rows_inserted = 0
    for idx, row in df.iterrows():
        kwargs: Dict[str, Any] = {"row_number": int(idx) + 1}

        # source_file (present on RawDocket; absent on other RAW models)
        if hasattr(model_class, "source_file"):
            kwargs["source_file"] = filepath.name

        # Mapped columns
        for excel_col, canonical in col_map.items():
            kwargs[canonical] = _safe_str(row.get(excel_col))

        # Extra columns → JSON
        if extra_cols:
            extras = {}
            for ec in extra_cols:
                val = _safe_str(row.get(ec))
                if val is not None:
                    extras[ec] = val
            kwargs["extra_fields"] = extras if extras else None

        session.add(model_class(**kwargs))
        rows_inserted += 1

    session.commit()
    logger.info("  Inserted %d rows into %s", rows_inserted, model_class.__tablename__)
    return rows_inserted


# ── File configuration ───────────────────────────────────────────────

DATA_DIR = Path("/mnt/data")

# Each XLSX file has two sheets:
#   Sheet 0  = actual data rows       → DATA_FILE_CONFIG  (load_excel_to_raw)
#   Sheet 1  = column definitions      → SCHEMA_FILE_CONFIG (load_schema_to_raw)

SCHEMA_FILE_CONFIG = [
    {"glob": "Case_Table*.xlsx",         "label": "case_schema",      "sheet": "Field Names, Types, Labels"},
    {"glob": "Docket_Table*.xlsx",       "label": "docket_schema",    "sheet": "Field Names, Types"},
    {"glob": "Document_Table*.xlsx",     "label": "document_schema",  "sheet": "Field Names, Types, Labels"},
    {"glob": "Secondary_Source*.xlsx",   "label": "secondary_schema", "sheet": "Field Names, Types, Labels"},
]

DATA_FILE_CONFIG = [
    {
        "glob": "Case_Table*.xlsx",
        "model": RawCase,
        "aliases": CASE_ALIASES,
        "sheet": 0,
    },
    {
        "glob": "Docket_Table*.xlsx",
        "model": RawDocket,
        "aliases": DOCKET_ALIASES,
        "sheet": 0,
    },
    {
        "glob": "Document_Table*.xlsx",
        "model": RawDocument,
        "aliases": DOCUMENT_ALIASES,
        "sheet": 0,
    },
    {
        "glob": "Secondary_Source*.xlsx",
        "model": RawSecondarySource,
        "aliases": SECONDARY_SOURCE_ALIASES,
        "sheet": 0,
    },
]


def load_all_raw(session: Session, data_dir: Path = DATA_DIR) -> Dict[str, int]:
    """
    Load every recognised Excel file from *data_dir*.

    Each workbook has two sheets:
      Sheet 0 → actual data rows  → DATA_FILE_CONFIG models
      Sheet 1 → column definitions → raw_schema_field
    """
    results: Dict[str, int] = {}

    # ── Schema files (metadata sheet of each workbook) ────────────────
    for cfg in SCHEMA_FILE_CONFIG:
        matches = sorted(data_dir.glob(cfg["glob"]))
        if not matches:
            logger.warning("No schema file matching %s in %s", cfg["glob"], data_dir)
            continue
        fpath = matches[-1]
        count = load_schema_to_raw(session, fpath, sheet_name=cfg["sheet"])
        results[f"{fpath.name} (schema)"] = count

    # ── Data files (data sheet of each workbook) ──────────────────────
    for cfg in DATA_FILE_CONFIG:
        matches = sorted(data_dir.glob(cfg["glob"]))
        if not matches:
            logger.warning("No data file matching %s in %s", cfg["glob"], data_dir)
            continue
        fpath = matches[-1]
        count = load_excel_to_raw(session, fpath, cfg["model"], cfg["aliases"], sheet_name=cfg["sheet"])
        results[fpath.name] = count

    return results


# ── File-hash utilities ────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_file_hashes(data_dir: Path = DATA_DIR) -> Dict[str, str]:
    """
    Compute SHA-256 hashes for every recognised Excel file in *data_dir*.

    Returns ``{filename: sha256_hex}`` – stored in ``pipeline_runs.file_hashes``
    for schema drift detection across runs.
    """
    hashes: Dict[str, str] = {}
    all_globs = (
        [cfg["glob"] for cfg in SCHEMA_FILE_CONFIG]
        + [cfg["glob"] for cfg in DATA_FILE_CONFIG]
    )
    for glob in all_globs:
        for fpath in sorted(data_dir.glob(glob)):
            hashes[fpath.name] = _sha256(fpath)
    return hashes


def detect_schema_drift(
    session: Session,
    current_hashes: Dict[str, str],
) -> List[str]:
    """
    Compare *current_hashes* against the most recent successful pipeline run.

    Returns a list of human-readable drift messages (empty → no drift).
    Logs a loud WARNING for every changed or new file detected.
    """
    from db.models import PipelineRun  # avoid circular at module level
    from sqlalchemy import desc

    last_run = (
        session.query(PipelineRun)
        .filter(PipelineRun.status == "success", PipelineRun.file_hashes.isnot(None))
        .order_by(desc(PipelineRun.started_at))
        .first()
    )

    if last_run is None:
        logger.info("Schema drift detection: no previous successful run found – skipping.")
        return []

    prev: Dict[str, str] = last_run.file_hashes or {}
    messages: List[str] = []

    for fname, sha in current_hashes.items():
        if fname not in prev:
            msg = f"NEW file detected: {fname}"
            messages.append(msg)
            logger.warning("⚠️  SCHEMA DRIFT: %s", msg)
        elif prev[fname] != sha:
            msg = f"CHANGED file: {fname} (hash {prev[fname][:8]}… → {sha[:8]}…)"
            messages.append(msg)
            logger.warning("⚠️  SCHEMA DRIFT: %s – column order/set may have changed!", msg)

    for fname in prev:
        if fname not in current_hashes:
            msg = f"MISSING file vs last run: {fname}"
            messages.append(msg)
            logger.warning("⚠️  SCHEMA DRIFT: %s", msg)

    if not messages:
        logger.info("Schema drift detection: no changes detected vs last successful run.")

    return messages
