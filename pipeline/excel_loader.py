"""
Excel → RAW table loader.

Reads an Excel workbook, maps columns via fuzzy aliases, and bulk-inserts
into the appropriate raw_* table.  Unmapped columns are stored in the
JSON ``extra_fields`` column so no data is ever lost.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Type

import pandas as pd
from sqlalchemy.orm import Session

from db.models import RawCase, RawDocket, RawDocument, RawSecondarySource
from pipeline.column_map import (
    CASE_ALIASES, DOCKET_ALIASES, DOCUMENT_ALIASES, SECONDARY_SOURCE_ALIASES,
    build_column_map,
)

logger = logging.getLogger(__name__)


def _safe_str(val: Any) -> str | None:
    """Convert a cell value to string, handling NaN/None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val).strip() or None


def load_excel_to_raw(
    session: Session,
    filepath: Path,
    model_class: Type,
    aliases: Dict[str, list[str]],
) -> int:
    """
    Load a single Excel file into a RAW table.

    Returns the number of rows inserted.
    """
    logger.info("Loading %s → %s", filepath.name, model_class.__tablename__)

    df = pd.read_excel(filepath, engine="openpyxl")
    headers = list(df.columns)
    col_map = build_column_map(headers, aliases)

    mapped_cols = set(col_map.keys())
    extra_cols = [h for h in headers if h not in mapped_cols]

    logger.info("  Mapped columns : %s", {v: k for k, v in col_map.items()})
    if extra_cols:
        logger.info("  Extra columns  : %s", extra_cols)

    rows_inserted = 0
    for idx, row in df.iterrows():
        kwargs: Dict[str, Any] = {"row_number": int(idx) + 1}

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


# ── Convenience wrappers ─────────────────────────────────────────────

DATA_DIR = Path("/mnt/data")

FILE_CONFIG = [
    {
        "glob": "Case_Table*.xlsx",
        "model": RawCase,
        "aliases": CASE_ALIASES,
    },
    {
        "glob": "Docket_Table*.xlsx",
        "model": RawDocket,
        "aliases": DOCKET_ALIASES,
    },
    {
        "glob": "Document_Table*.xlsx",
        "model": RawDocument,
        "aliases": DOCUMENT_ALIASES,
    },
    {
        "glob": "Secondary_Source*.xlsx",
        "model": RawSecondarySource,
        "aliases": SECONDARY_SOURCE_ALIASES,
    },
]


def load_all_raw(session: Session, data_dir: Path = DATA_DIR) -> Dict[str, int]:
    """Load every recognised Excel file from *data_dir* into RAW tables."""
    results: Dict[str, int] = {}
    for cfg in FILE_CONFIG:
        matches = sorted(data_dir.glob(cfg["glob"]))
        if not matches:
            logger.warning("No file matching %s in %s", cfg["glob"], data_dir)
            continue
        fpath = matches[-1]  # newest if multiple
        count = load_excel_to_raw(session, fpath, cfg["model"], cfg["aliases"])
        results[fpath.name] = count
    return results
