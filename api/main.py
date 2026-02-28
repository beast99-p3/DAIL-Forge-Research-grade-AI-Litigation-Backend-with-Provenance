"""
DAIL Forge – FastAPI application entry-point.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes_research import router as research_router
from api.routes_curation import router as curation_router
from api.routes_pipeline import router as pipeline_router
from api.routes_stats import router as stats_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="DAIL Forge",
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

# Serve static assets (CSS, JS, images if any)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", tags=["UI"], include_in_schema=False)
async def serve_frontend():
    """Serve the single-page frontend."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    return {"service": "DAIL Forge", "version": "0.1.0", "ui": "Place static/index.html to enable"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
