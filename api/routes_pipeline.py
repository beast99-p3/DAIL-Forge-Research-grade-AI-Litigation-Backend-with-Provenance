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
from api.schemas import DeltaSummary
from db.models import PipelineRun
from db.session import SyncSessionLocal
from pipeline.excel_loader import (
    load_all_raw, compute_file_hashes, detect_schema_drift, DATA_DIR,
)
from pipeline.delta_loader import load_all_raw_delta
from pipeline.snapshot import take_snapshot
from pipeline.transform import transform_all
from pipeline.validate import validate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pipeline"], dependencies=[Depends(require_api_key)])


@router.post("/pipeline/load", status_code=200)
async def trigger_pipeline():
    """
    Run the full Excel → RAW → CURATED pipeline (full reload).

    On success an automatic snapshot of the curated layer is taken so
    researchers can later diff this run against future runs.
    """
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

        # ── Auto-snapshot the curated layer on success ────────────
        if pipeline_run.status == "success":
            try:
                snap = take_snapshot(
                    session,
                    label=f"Auto – pipeline run {run_id[:8]}",
                    run_id=run_id,
                    description="Automatic snapshot taken at end of full pipeline load.",
                    is_auto=True,
                )
                session.commit()
                snapshot_id = snap.id
            except Exception:
                logger.warning("Auto-snapshot failed (non-fatal)", exc_info=True)
                snapshot_id = None
        else:
            snapshot_id = None

        return {
            "run_id": run_id,
            "status": pipeline_run.status,
            "schema_drift": drift,
            "raw_loaded": raw_counts,
            "curated_transformed": curated_counts,
            "snapshot_id": snapshot_id,
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


@router.post("/pipeline/load-delta", status_code=200, response_model=None)
async def trigger_pipeline_delta():
    """
    Incremental / Delta pipeline run.

    Instead of reloading every row, computes a SHA-256 checksum for each
    incoming Excel row, compares it against the stored checksum for that
    row, and only writes rows that are new or changed.

    Every processed row produces one ``RawDeltaLog`` entry so you can
    later answer: *"which rows changed between run A and run B?"*

    On success an automatic curated-layer snapshot is taken, enabling
    ``GET /snapshots/{id}/diff`` to show exactly what changed.
    """
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

        # ── Delta load of RAW tables ──────────────────────────────
        delta_results = load_all_raw_delta(session, run_id=run_id, data_dir=DATA_DIR)
        pipeline_run.raw_counts = {
            fname: sum(counts.values()) for fname, counts in delta_results.items()
        }
        session.commit()

        # ── Transform only if anything changed ────────────────────
        total_changes = sum(
            v.get("insert", 0) + v.get("update", 0)
            for v in delta_results.values()
        )
        if total_changes > 0:
            curated_counts = transform_all(session, run_id=run_id)
        else:
            curated_counts = {"message": "no raw changes – transform skipped"}
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

        # ── Delta summary ──────────────────────────────────────────
        total_insert = sum(v.get("insert", 0) for v in delta_results.values())
        total_update = sum(v.get("update", 0) for v in delta_results.values())
        total_skip   = sum(v.get("skip",   0) for v in delta_results.values())

        delta_summary = DeltaSummary(
            run_id=run_id,
            total_rows_scanned=total_insert + total_update + total_skip,
            inserted=total_insert,
            updated=total_update,
            skipped=total_skip,
            by_file=delta_results,
        )

        # ── Auto-snapshot ──────────────────────────────────────────
        snapshot_id = None
        if pipeline_run.status == "success":
            try:
                snap = take_snapshot(
                    session,
                    label=f"Auto (delta) – run {run_id[:8]}",
                    run_id=run_id,
                    description=(
                        f"Auto snapshot after delta load: "
                        f"{total_insert} inserted, {total_update} updated, "
                        f"{total_skip} skipped."
                    ),
                    is_auto=True,
                )
                session.commit()
                snapshot_id = snap.id
            except Exception:
                logger.warning("Auto-snapshot failed (non-fatal)", exc_info=True)

        return {
            "run_id": run_id,
            "status": pipeline_run.status,
            "schema_drift": drift,
            "delta": delta_summary.model_dump(),
            "curated_transformed": curated_counts,
            "snapshot_id": snapshot_id,
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
        logger.exception("Delta pipeline failed")
        raise HTTPException(500, f"Pipeline error: {e}")
    finally:
        session.close()



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

