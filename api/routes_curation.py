"""
Curation API – restricted write endpoints with provenance enforcement.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Case, CaseTag, Tag, Citation, ChangeLog, CaseCaptionHistory
from db.session import get_async_session
from api.auth import require_api_key
from api.schemas import (
    CasePatch, CaseOut, CaseTagCreate, TagOut,
    CitationCreate, CitationOut, ChangeLogOut,
)

router = APIRouter(tags=["Curation (restricted write)"], dependencies=[Depends(require_api_key)])


# ── Helpers ──────────────────────────────────────────────────────────

async def _get_case_or_404(session: AsyncSession, case_id: int) -> Case:
    result = await session.execute(select(Case).filter(Case.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    return case


def _validate_provenance(citation_id, citation_justification):
    """At least one of citation_id or citation_justification must be provided."""
    if citation_id is None and not citation_justification:
        raise HTTPException(
            422,
            "Provenance required: supply either citation_id or citation_justification",
        )


async def _log_change(
    session: AsyncSession,
    table_name: str,
    record_id: int,
    field_name: str,
    old_value,
    new_value,
    editor_id: str,
    reason: str,
    citation_id=None,
    citation_justification=None,
):
    entry = ChangeLog(
        table_name=table_name,
        record_id=record_id,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        editor_id=editor_id,
        reason=reason,
        citation_id=citation_id,
        citation_justification=citation_justification,
    )
    session.add(entry)
    return entry


# ── PATCH /cases/{case_id} ───────────────────────────────────────────

@router.patch("/cases/{case_id}", response_model=CaseOut)
async def update_case(
    case_id: int,
    body: CasePatch,
    session: AsyncSession = Depends(get_async_session),
):
    _validate_provenance(body.citation_id, body.citation_justification)
    case = await _get_case_or_404(session, case_id)

    updatable = [
        "case_name", "court", "filing_date", "closing_date",
        "case_status", "case_outcome", "case_type",
        "plaintiff", "defendant", "judge", "summary",
    ]

    changes = 0
    for field in updatable:
        new_val = getattr(body, field, None)
        if new_val is None:
            continue
        old_val = getattr(case, field)
        if str(old_val) == str(new_val):
            continue

        # Track caption changes separately
        if field == "case_name":
            session.add(CaseCaptionHistory(
                case_id=case.id,
                old_caption=old_val,
                new_caption=str(new_val),
                changed_by=body.editor_id,
                reason=body.reason,
            ))

        await _log_change(
            session, "cases", case.id, field,
            old_val, new_val,
            body.editor_id, body.reason,
            body.citation_id, body.citation_justification,
        )
        setattr(case, field, new_val)
        changes += 1

    if changes == 0:
        raise HTTPException(400, "No fields changed")

    await session.commit()
    await session.refresh(case)
    return case


# ── POST /cases/{case_id}/tags ───────────────────────────────────────

@router.post("/cases/{case_id}/tags", response_model=TagOut, status_code=201)
async def add_case_tag(
    case_id: int,
    body: CaseTagCreate,
    session: AsyncSession = Depends(get_async_session),
):
    _validate_provenance(body.citation_id, body.citation_justification)
    case = await _get_case_or_404(session, case_id)

    # Get or create tag
    result = await session.execute(
        select(Tag).filter_by(tag_type=body.tag_type, value=body.value)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        tag = Tag(tag_type=body.tag_type, value=body.value)
        session.add(tag)
        await session.flush()

    # Check duplicate link
    existing = await session.execute(
        select(CaseTag).filter_by(case_id=case.id, tag_id=tag.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Tag already linked to this case")

    session.add(CaseTag(case_id=case.id, tag_id=tag.id))

    await _log_change(
        session, "case_tags", case.id,
        f"tag:{body.tag_type}", None, body.value,
        body.editor_id, body.reason,
        body.citation_id, body.citation_justification,
    )

    await session.commit()
    return tag


# ── POST /citations ──────────────────────────────────────────────────

@router.post("/citations", response_model=CitationOut, status_code=201)
async def create_citation(
    body: CitationCreate,
    session: AsyncSession = Depends(get_async_session),
):
    citation = Citation(
        source_type=body.source_type,
        source_ref=body.source_ref,
        description=body.description,
        accessed_at=body.accessed_at,
    )
    session.add(citation)
    await session.commit()
    await session.refresh(citation)
    return citation
