"""
Master pipeline entry-point  (schema-aware v2).

Usage (inside container):
    python -m pipeline.load_all

Pipeline stages
---------------
1. Load Excel → RAW  (schema metadata + data files)
2. Synthesise stub cases from FK references
3. Transform RAW data → CURATED
4. Validate
"""

import logging
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from db.session import SyncSessionLocal
from pipeline.excel_loader import load_all_raw, DATA_DIR
from pipeline.transform import transform_all
from pipeline.validate import validate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
logger = logging.getLogger("pipeline")


def run(data_dir: Path = DATA_DIR) -> None:
    logger.info("=" * 60)
    logger.info("DAIL Forge – Pipeline (schema-aware v2)")
    logger.info("  load → stub-synthesis → transform → validate")
    logger.info("Data directory: %s", data_dir)
    logger.info("=" * 60)

    session: Session = SyncSessionLocal()
    try:
        # Step 1 – Load Excel → RAW tables
        logger.info("── Step 1: Excel → RAW tables ──")
        logger.info("  Schema files → raw_schema_field")
        logger.info("  Data files   → raw_document / raw_secondary_source")
        raw_counts = load_all_raw(session, data_dir)
        for fname, cnt in raw_counts.items():
            logger.info("  %s: %d rows", fname, cnt)

        if not raw_counts:
            logger.error("No Excel files found in %s – aborting.", data_dir)
            sys.exit(1)

        # Step 2 – Stub synthesis + Transform RAW → CURATED
        logger.info("── Step 2: Stub synthesis + RAW → CURATED ──")
        curated_counts = transform_all(session)
        for table, cnt in curated_counts.items():
            logger.info("  %s: %d rows", table, cnt)

        # Step 3 – Validate
        logger.info("── Step 3: Validation ──")
        issues = validate(session)
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        logger.info("  %d errors, %d warnings", len(errors), len(warnings))

        logger.info("=" * 60)
        logger.info("Pipeline complete.")
    except Exception:
        session.rollback()
        logger.exception("Pipeline failed!")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    run()
