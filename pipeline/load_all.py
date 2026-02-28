"""
Master pipeline entry-point  (schema-aware v2).

Usage (inside container):
    python -m pipeline.load_all

Pipeline stages
---------------
1. Compute file hashes + schema drift detection
2. Load Excel → RAW  (schema metadata + data files)
3. Synthesise stub cases from FK references
4. Transform RAW data → CURATED
5. Validate

Every run is registered in the ``pipeline_runs`` table so changes in
``change_log`` can be traced back to the exact pipeline execution.
"""

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from db.session import SyncSessionLocal
from db.models import PipelineRun
from pipeline.excel_loader import (
    load_all_raw, compute_file_hashes, detect_schema_drift, DATA_DIR,
)
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
    logger.info("  hash → load → stub-synthesis → transform → validate")
    logger.info("Data directory: %s", data_dir)
    logger.info("=" * 60)

    run_id = str(uuid.uuid4())
    session: Session = SyncSessionLocal()

    # Register the run immediately so change_log rows have a valid run_id
    pipeline_run = PipelineRun(
        run_id=run_id,
        status="running",
        data_dir=str(data_dir),
    )
    session.add(pipeline_run)
    session.commit()
    logger.info("Pipeline run registered: %s", run_id)

    try:
        # Step 1 – File hashes + schema drift detection
        logger.info("── Step 1: File hashes + schema drift detection ──")
        file_hashes = compute_file_hashes(data_dir)
        if not file_hashes:
            logger.error("No Excel files found in %s – aborting.", data_dir)
            pipeline_run.status = "failed"
            pipeline_run.notes = "No Excel files found in data directory"
            session.commit()
            sys.exit(1)
        drift_messages = detect_schema_drift(session, file_hashes)
        if drift_messages:
            logger.warning("  Schema drift detected: %d change(s)", len(drift_messages))
        pipeline_run.file_hashes = file_hashes
        session.commit()

        # Step 2 – Load Excel → RAW tables
        logger.info("── Step 2: Excel → RAW tables ──")
        raw_counts = load_all_raw(session, data_dir)
        for fname, cnt in raw_counts.items():
            logger.info("  %s: %d rows", fname, cnt)
        pipeline_run.raw_counts = raw_counts
        session.commit()

        # Step 3 – Stub synthesis + Transform RAW → CURATED
        logger.info("── Step 3: Stub synthesis + RAW → CURATED ──")
        curated_counts = transform_all(session, run_id=run_id)
        for table, cnt in curated_counts.items():
            logger.info("  %s: %d rows", table, cnt)
        pipeline_run.curated_counts = curated_counts
        session.commit()

        # Step 4 – Validate
        logger.info("── Step 4: Validation ──")
        issues = validate(session)
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        logger.info("  %d errors, %d warnings", len(errors), len(warnings))

        pipeline_run.error_count = len(errors)
        pipeline_run.warning_count = len(warnings)
        pipeline_run.status = "failed" if errors else "success"
        pipeline_run.finished_at = datetime.now(timezone.utc)
        if drift_messages:
            pipeline_run.notes = "Schema drift: " + "; ".join(drift_messages)
        session.commit()

        if errors:
            logger.error("Pipeline finished with %d integrity error(s) – status=failed", len(errors))
        else:
            logger.info("=" * 60)
            logger.info("Pipeline complete – status=success  run_id=%s", run_id)
    except Exception:
        session.rollback()
        try:
            pipeline_run.status = "failed"
            pipeline_run.finished_at = datetime.now(timezone.utc)
            session.commit()
        except Exception:
            pass
        logger.exception("Pipeline failed!")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    run()

