"""
Pipeline API – trigger data loading from the API.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_api_key
from db.models import PipelineRun
from db.session import SyncSessionLocal
from pipeline.excel_loader import (
    load_all_raw, compute_file_hashes, detect_schema_drift, DATA_DIR,
)
from pipeline.transform import transform_all
from pipeline.validate import validate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pipeline"], dependencies=[Depends(require_api_key)])


@router.post("/pipeline/load", status_code=200)
async def trigger_pipeline():
    """Run the full Excel → RAW → stub-synthesis → CURATED pipeline."""
    run_id = str(uuid.uuid4())
    session = SyncSessionLocal()
    try:
        pipeline_run = PipelineRun(
            run_id=run_id, status="running", data_dir=str(DATA_DIR)
        )
        session.add(pipeline_run)
        session.commit()

        file_hashes = compute_file_hashes(DATA_DIR)
        drift = detect_schema_drift(session, file_hashes)
        pipeline_run.file_hashes = file_hashes
        session.commit()

        raw_counts = load_all_raw(session, DATA_DIR)
        pipeline_run.raw_counts = raw_counts
        session.commit()

        curated_counts = transform_all(session, run_id=run_id)
        pipeline_run.curated_counts = curated_counts
        session.commit()

        issues = validate(session)
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]

        pipeline_run.error_count = len(errors)
        pipeline_run.warning_count = len(warnings)
        pipeline_run.status = "failed" if errors else "success"
        pipeline_run.finished_at = datetime.now(timezone.utc)
        if drift:
            pipeline_run.notes = "Schema drift: " + "; ".join(drift)
        session.commit()

        return {
            "run_id": run_id,
            "status": pipeline_run.status,
            "schema_drift": drift,
            "raw_loaded": raw_counts,
            "curated_transformed": curated_counts,
            "validation_issues": [
                {"level": i.level, "check": i.check, "message": i.message}
                for i in issues
            ],
        }
    except Exception as e:
        session.rollback()
        try:
            pipeline_run.status = "failed"
            pipeline_run.finished_at = datetime.now(timezone.utc)
            session.commit()
        except Exception:
            pass
        logger.exception("Pipeline failed")
        raise HTTPException(500, f"Pipeline error: {e}")
    finally:
        session.close()

