"""
Saved Views API – CRUD for named filter presets.

A "saved view" stores a complete set of search filters + sort settings so
researchers can bookmark and share complex queries by name.

Public endpoints (no auth):
  GET  /views               – list all saved views
  GET  /views/{name}        – retrieve a view and its filters
  POST /views/{name}/apply  – return /cases results for a stored view

Protected endpoints (API key required):
  POST   /views             – create a new view
  PUT    /views/{name}      – update an existing view
  DELETE /views/{name}      – delete a view
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.schemas import SavedViewCreate, SavedViewOut
from db.models import SavedView
from db.session import get_async_session

router = APIRouter(prefix="/views", tags=["Saved Views"])


# ── Public ────────────────────────────────────────────────────────────

@router.get("", response_model=list[SavedViewOut])
async def list_views(session: AsyncSession = Depends(get_async_session)):
    """Return all saved views, ordered by name."""
    result = await session.execute(
        select(SavedView).order_by(SavedView.name)
    )
    return result.scalars().all()


@router.get("/{name}", response_model=SavedViewOut)
async def get_view(name: str, session: AsyncSession = Depends(get_async_session)):
    """Retrieve a saved view by its unique name."""
    result = await session.execute(
        select(SavedView).where(SavedView.name == name)
    )
    view = result.scalar_one_or_none()
    if not view:
        raise HTTPException(404, f"View '{name}' not found")
    return view


# ── Protected ────────────────────────────────────────────────────────

@router.post("", response_model=SavedViewOut, status_code=201,
             dependencies=[Depends(require_api_key)])
async def create_view(
    payload: SavedViewCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create a new saved view.

    ``filters`` is a free-form JSON object matching the query-param names
    accepted by ``GET /cases`` (e.g. ``{"court": "S.D.N.Y.", "is_stub": false}``).
    """
    existing = (
        await session.execute(select(SavedView).where(SavedView.name == payload.name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"A view named '{payload.name}' already exists. "
                                 "Use PUT /views/{name} to update it.")

    view = SavedView(
        name=payload.name,
        description=payload.description,
        filters=payload.filters,
        sort_by=payload.sort_by,
        sort_dir=payload.sort_dir,
        columns=payload.columns,
    )
    session.add(view)
    await session.commit()
    await session.refresh(view)
    return view


@router.put("/{name}", response_model=SavedViewOut,
            dependencies=[Depends(require_api_key)])
async def update_view(
    name: str,
    payload: SavedViewCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update an existing saved view. Replaces all fields."""
    result = await session.execute(select(SavedView).where(SavedView.name == name))
    view = result.scalar_one_or_none()
    if not view:
        raise HTTPException(404, f"View '{name}' not found")

    view.name        = payload.name
    view.description = payload.description
    view.filters     = payload.filters
    view.sort_by     = payload.sort_by
    view.sort_dir    = payload.sort_dir
    view.columns     = payload.columns
    view.updated_at  = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(view)
    return view


@router.delete("/{name}", status_code=204,
               dependencies=[Depends(require_api_key)])
async def delete_view(
    name: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a saved view by name."""
    result = await session.execute(select(SavedView).where(SavedView.name == name))
    view = result.scalar_one_or_none()
    if not view:
        raise HTTPException(404, f"View '{name}' not found")
    await session.delete(view)
    await session.commit()
