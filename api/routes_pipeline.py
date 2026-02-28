"""
Pipeline API – trigger data loading from the API.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_api_key
from db.session import SyncSessionLocal
from pipeline.excel_loader import load_all_raw, DATA_DIR
from pipeline.transform import transform_all
from pipeline.validate import validate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pipeline"], dependencies=[Depends(require_api_key)])


@router.post("/pipeline/load", status_code=200)
async def trigger_pipeline():
    """Run the full Excel → RAW → CURATED pipeline."""
    session = SyncSessionLocal()
    try:
        raw_counts = load_all_raw(session, DATA_DIR)
        curated_counts = transform_all(session)
        issues = validate(session)
        return {
            "raw_loaded": raw_counts,
            "curated_transformed": curated_counts,
            "validation_issues": [
                {"level": i.level, "check": i.check, "message": i.message}
                for i in issues
            ],
        }
    except Exception as e:
        session.rollback()
        logger.exception("Pipeline failed")
        raise HTTPException(500, f"Pipeline error: {e}")
    finally:
        session.close()
