"""
Stats API – dashboard data for the frontend.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Case, Docket, Document, SecondarySource, Tag, CaseTag, ChangeLog
from db.session import get_async_session

router = APIRouter(tags=["Stats"])


@router.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_async_session)):
    """Return aggregate counts for the dashboard."""
    cases = (await session.execute(select(func.count(Case.id)))).scalar_one()
    dockets = (await session.execute(select(func.count(Docket.id)))).scalar_one()
    documents = (await session.execute(select(func.count(Document.id)))).scalar_one()
    sources = (await session.execute(select(func.count(SecondarySource.id)))).scalar_one()
    tags = (await session.execute(select(func.count(Tag.id)))).scalar_one()
    changes = (await session.execute(select(func.count(ChangeLog.id)))).scalar_one()

    # Tag distribution – top 30 tags by frequency
    tag_dist_stmt = (
        select(Tag.tag_type, Tag.value, func.count(CaseTag.id).label("cnt"))
        .join(CaseTag, CaseTag.tag_id == Tag.id)
        .group_by(Tag.tag_type, Tag.value)
        .order_by(func.count(CaseTag.id).desc())
        .limit(30)
    )
    tag_dist = (await session.execute(tag_dist_stmt)).all()

    return {
        "cases": cases,
        "dockets": dockets,
        "documents": documents,
        "secondary_sources": sources,
        "tags": tags,
        "change_log_entries": changes,
        "tag_distribution": [
            {"tag_type": td.tag_type, "value": td.value, "count": td.cnt}
            for td in tag_dist
        ],
    }


@router.get("/stats/recent-changes")
async def get_recent_changes(
    session: AsyncSession = Depends(get_async_session),
    limit: int = 10,
):
    """Return the most recent change_log entries."""
    stmt = (
        select(ChangeLog)
        .order_by(ChangeLog.changed_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "table_name": e.table_name,
            "record_id": e.record_id,
            "field_name": e.field_name,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "editor_id": e.editor_id,
            "reason": e.reason,
            "citation_id": e.citation_id,
            "citation_justification": e.citation_justification,
            "changed_at": e.changed_at.isoformat() if e.changed_at else None,
        }
        for e in entries
    ]
