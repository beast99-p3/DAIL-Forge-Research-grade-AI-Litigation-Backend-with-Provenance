"""Pydantic response / request schemas for the DAIL Forge API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, Field


# ── Tags ─────────────────────────────────────────────────────────────

class TagOut(BaseModel):
    id: int
    tag_type: str
    value: str

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    tag_type: str = Field(..., description="One of: issue, area, cause, algorithm, harm")
    value: str


# ── Cases ────────────────────────────────────────────────────────────

class CaseBase(BaseModel):
    case_id: str
    case_name: Optional[str] = None
    court: Optional[str] = None
    filing_date: Optional[date] = None
    closing_date: Optional[date] = None
    case_status: Optional[str] = None
    case_outcome: Optional[str] = None
    case_type: Optional[str] = None
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    judge: Optional[str] = None
    summary: Optional[str] = None
    is_stub: bool = False


class CaseOut(CaseBase):
    id: int
    tags: List[TagOut] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CaseListOut(BaseModel):
    """Paginated list wrapper."""
    total: int
    page: int
    page_size: int
    items: List[CaseOut]


class CasePatch(BaseModel):
    """Fields that curators can update."""
    case_name: Optional[str] = None
    court: Optional[str] = None
    filing_date: Optional[date] = None
    closing_date: Optional[date] = None
    case_status: Optional[str] = None
    case_outcome: Optional[str] = None
    case_type: Optional[str] = None
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    judge: Optional[str] = None
    summary: Optional[str] = None

    # Provenance (required for every write)
    editor_id: str = Field(..., description="Identifier of the person making the edit")
    reason: str = Field(..., description="Why this change is being made")
    citation_id: Optional[int] = Field(None, description="FK to citations table")
    citation_justification: Optional[str] = Field(
        None, description="Required when citation_id is null"
    )


# ── Dockets ──────────────────────────────────────────────────────────

class DocketOut(BaseModel):
    id: int
    docket_number: Optional[str] = None
    entry_date: Optional[date] = None
    entry_text: Optional[str] = None
    filed_by: Optional[str] = None

    class Config:
        from_attributes = True


# ── Documents ────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: int
    document_title: Optional[str] = None
    document_type: Optional[str] = None
    document_date: Optional[date] = None
    url: Optional[str] = None

    class Config:
        from_attributes = True


# ── Secondary Sources ────────────────────────────────────────────────

class SecondarySourceOut(BaseModel):
    id: int
    source_title: Optional[str] = None
    source_type: Optional[str] = None
    publication_date: Optional[date] = None
    author: Optional[str] = None
    url: Optional[str] = None

    class Config:
        from_attributes = True


# ── Citations ────────────────────────────────────────────────────────

class CitationCreate(BaseModel):
    source_type: str = Field(..., description="e.g. court_filing, news, docket")
    source_ref: str = Field(..., description="URL or document identifier")
    description: Optional[str] = None
    accessed_at: Optional[datetime] = None


class CitationOut(BaseModel):
    id: int
    source_type: str
    source_ref: str
    description: Optional[str] = None
    accessed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Change Log ───────────────────────────────────────────────────────

class ChangeLogOut(BaseModel):
    id: int
    table_name: str
    record_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    editor_id: str
    reason: str
    citation_id: Optional[int] = None
    citation_justification: Optional[str] = None
    changed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Provenance for tag additions ─────────────────────────────────────

class CaseTagCreate(BaseModel):
    tag_type: str = Field(..., description="One of: issue, area, cause, algorithm, harm")
    value: str
    editor_id: str
    reason: str
    citation_id: Optional[int] = None
    citation_justification: Optional[str] = None
