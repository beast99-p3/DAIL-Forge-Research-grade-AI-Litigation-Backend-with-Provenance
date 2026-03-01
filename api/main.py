"""
DAIL Forge – FastAPI application entry-point.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes_research import router as research_router
from api.routes_curation import router as curation_router
from api.routes_pipeline import router as pipeline_router
from api.routes_stats import router as stats_router
from api.routes_views import router as views_router
from api.routes_snapshots import router as snapshots_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-load Excel data on first startup if the database is empty."""
    try:
        import uuid
        from datetime import datetime, timezone
        from db.session import SyncSessionLocal
        from db.models import RawDocument, PipelineRun
        from pipeline.excel_loader import (
            load_all_raw, compute_file_hashes, detect_schema_drift, DATA_DIR,
        )
        from pipeline.transform import transform_all
        from pipeline.validate import validate
        from api.config import get_settings

        settings = get_settings()
        session = SyncSessionLocal()
        try:
            count = session.query(RawDocument).count()
            if count == 0:
                logger.info("Database is empty – running pipeline auto-load from %s", DATA_DIR)
                run_id = str(uuid.uuid4())
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

                logger.info(
                    "Auto-load complete: raw=%s  curated=%s  errors=%d  warnings=%d",
                    raw_counts, curated_counts, len(errors), len(warnings),
                )

                if errors and not settings.DAIL_ALLOW_DIRTY_STARTUP:
                    err_summary = "; ".join(f"{e.check}: {e.message}" for e in errors)
                    raise RuntimeError(
                        f"Pipeline integrity errors block startup "
                        f"(set DAIL_ALLOW_DIRTY_STARTUP=true to override): {err_summary}"
                    )
            else:
                # DB has data — check if enrichment step still needs to run
                # (cases with no court means extra_fields were never extracted)
                from db.models import Case
                from pipeline.transform import enrich_cases_from_raw_documents
                unenriched = session.query(Case).filter(Case.court.is_(None)).count()
                if unenriched > 0:
                    logger.info(
                        "%d cases have no court data – running enrichment from extra_fields",
                        unenriched,
                    )
                    enriched = enrich_cases_from_raw_documents(session)
                    logger.info("Enrichment complete: %d cases updated", enriched)
                else:
                    logger.info(
                        "Database already contains data – skipping auto-load (raw_document rows: %d)", count
                    )
        except RuntimeError:
            raise
        except Exception:
            session.rollback()
            logger.exception("Auto-load pipeline failed – the API will still start")
        finally:
            session.close()
    except RuntimeError as exc:
        logger.critical("STARTUP BLOCKED: %s", exc)
        raise
    except Exception:
        logger.exception("Could not check database during startup")

    yield  # application runs here


app = FastAPI(
    title="DAIL Forge",
    lifespan=lifespan,
    description=(
        "Research-grade API for the Database of AI Litigation (DAIL). "
        "Public read endpoints for researchers + restricted curation endpoints "
        "with a provenance ledger (change_log + citations)."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(research_router)
app.include_router(curation_router)
app.include_router(pipeline_router)
app.include_router(stats_router)
app.include_router(views_router)
app.include_router(snapshots_router)

# Serve static assets (CSS, JS, images if any)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", tags=["UI"], include_in_schema=False)
async def serve_frontend():
    """Serve the single-page frontend."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(
            str(index),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return {"service": "DAIL Forge", "version": "0.1.0", "ui": "Place static/index.html to enable"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
