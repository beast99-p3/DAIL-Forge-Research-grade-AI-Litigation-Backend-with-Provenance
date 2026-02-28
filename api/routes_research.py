"""
Research API – public read / filter / export endpoints.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Case, CaseTag, Tag, Docket, Document, SecondarySource, ChangeLog
from db.session import get_async_session
from api.schemas import (
    CaseOut, CaseListOut, DocketOut, DocumentOut, SecondarySourceOut, TagOut,
    ChangeLogOut,
)

router = APIRouter(tags=["Research (public read)"])


# ── Helpers ──────────────────────────────────────────────────────────

def _case_query(
    tag_type: Optional[str] = None,
    tag_value: Optional[str] = None,
    court: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """Build a SELECT for cases with optional filters."""
    stmt = select(Case).options(
        selectinload(Case.tags).selectinload(CaseTag.tag)
    )

    if tag_type and tag_value:
        stmt = stmt.join(Case.tags).join(CaseTag.tag).filter(
            Tag.tag_type == tag_type, Tag.value.ilike(f"%{tag_value}%")
        )
    elif tag_type:
        stmt = stmt.join(Case.tags).join(CaseTag.tag).filter(Tag.tag_type == tag_type)
    elif tag_value:
        stmt = stmt.join(Case.tags).join(CaseTag.tag).filter(Tag.value.ilike(f"%{tag_value}%"))

    if court:
        stmt = stmt.filter(Case.court.ilike(f"%{court}%"))
    if date_from:
        stmt = stmt.filter(Case.filing_date >= date_from)
    if date_to:
        stmt = stmt.filter(Case.filing_date <= date_to)
    if status:
        stmt = stmt.filter(Case.case_status.ilike(f"%{status}%"))
    if outcome:
        stmt = stmt.filter(Case.case_outcome.ilike(f"%{outcome}%"))
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.filter(
            or_(
                Case.case_name.ilike(pattern),
                Case.plaintiff.ilike(pattern),
                Case.defendant.ilike(pattern),
                Case.summary.ilike(pattern),
            )
        )

    return stmt


def _case_to_out(c: Case) -> CaseOut:
    tags = [TagOut(id=ct.tag.id, tag_type=ct.tag.tag_type, value=ct.tag.value) for ct in c.tags]
    return CaseOut(
        id=c.id, case_id=c.case_id, case_name=c.case_name, court=c.court,
        filing_date=c.filing_date, closing_date=c.closing_date,
        case_status=c.case_status, case_outcome=c.case_outcome,
        case_type=c.case_type, plaintiff=c.plaintiff, defendant=c.defendant,
        judge=c.judge, summary=c.summary, tags=tags,
        created_at=c.created_at, updated_at=c.updated_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/cases", response_model=CaseListOut)
async def list_cases(
    session: AsyncSession = Depends(get_async_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort_by: str = Query("filing_date", description="Sort field"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    tag_type: Optional[str] = None,
    tag_value: Optional[str] = None,
    court: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    keyword: Optional[str] = None,
):
    base = _case_query(tag_type, tag_value, court, date_from, date_to, status, outcome, keyword)

    # Total count
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # Sorting
    sort_col = getattr(Case, sort_by, Case.filing_date)
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    stmt = base.order_by(order).offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    cases = result.unique().scalars().all()

    return CaseListOut(
        total=total, page=page, page_size=page_size,
        items=[_case_to_out(c) for c in cases],
    )


@router.get("/cases/{case_id}", response_model=CaseOut)
async def get_case(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(Case).options(
        selectinload(Case.tags).selectinload(CaseTag.tag)
    ).filter(Case.id == case_id)
    result = await session.execute(stmt)
    case = result.unique().scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    return _case_to_out(case)


@router.get("/cases/{case_id}/dockets", response_model=list[DocketOut])
async def get_case_dockets(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(Docket).filter(Docket.case_id == case_id).order_by(Docket.entry_date.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/cases/{case_id}/documents", response_model=list[DocumentOut])
async def get_case_documents(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(Document).filter(Document.case_id == case_id).order_by(Document.document_date.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/cases/{case_id}/secondary-sources", response_model=list[SecondarySourceOut])
async def get_case_secondary_sources(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(SecondarySource).filter(SecondarySource.case_id == case_id)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/cases/{case_id}/change-log", response_model=list[ChangeLogOut])
async def get_case_change_log(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = (
        select(ChangeLog)
        .filter(ChangeLog.table_name == "cases", ChangeLog.record_id == case_id)
        .order_by(ChangeLog.changed_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# ── CSV export ───────────────────────────────────────────────────────

@router.get("/export/cases.csv")
async def export_cases_csv(
    session: AsyncSession = Depends(get_async_session),
    tag_type: Optional[str] = None,
    tag_value: Optional[str] = None,
    court: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    keyword: Optional[str] = None,
):
    stmt = _case_query(tag_type, tag_value, court, date_from, date_to, status, outcome, keyword)
    stmt = stmt.order_by(Case.filing_date.desc())
    result = await session.execute(stmt)
    cases = result.unique().scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = [
        "id", "case_id", "case_name", "court", "filing_date", "closing_date",
        "case_status", "case_outcome", "case_type", "plaintiff", "defendant",
        "judge", "summary", "tags",
    ]
    writer.writerow(header)

    for c in cases:
        tags_str = "; ".join(f"{ct.tag.tag_type}:{ct.tag.value}" for ct in c.tags)
        writer.writerow([
            c.id, c.case_id, c.case_name, c.court, c.filing_date, c.closing_date,
            c.case_status, c.case_outcome, c.case_type, c.plaintiff, c.defendant,
            c.judge, c.summary, tags_str,
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cases.csv"},
    )
