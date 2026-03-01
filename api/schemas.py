"""Pydantic response / request schemas for the DAIL Forge API."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ── Tags ─────────────────────────────────────────────────────────────

class TagOut(BaseModel):
    id: int
    tag_type: str
    value: str
    slug: Optional[str] = None
    is_official: bool = True
    source: Optional[str] = None

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    tag_type: str = Field(..., description="One of: issue, area, cause, algorithm, harm")
    value: str


# ── Cases ────────────────────────────────────────────────────────────

class CaseBase(BaseModel):
    case_id: str
    legacy_case_number: Optional[str] = None
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
    case_fingerprint: Optional[str] = None


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
    actor_type: str = "human"
    operation: str = "update"
    run_id: Optional[str] = None
    changed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Provenance for tag additions ─────────────────────────────────────

class CaseTagCreate(BaseModel):
    tag_type: str = Field(..., description="One of: issue, area, cause, algorithm, harm")
    value: str
    is_official: bool = Field(True, description="False marks the tag for curator review")
    editor_id: str
    reason: str
    citation_id: Optional[int] = None
    citation_justification: Optional[str] = None


# ── Case Promote (stub → canonical) ──────────────────────────────────

class CasePromoteIn(BaseModel):
    """Payload for POST /cases/{id}/promote.

    Promotes a stub case into a real case record, locks the legacy number,
    and records a merge/provenance event in change_log.
    """
    case_name: str = Field(..., description="Official case caption")
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

    # Provenance (required)
    editor_id: str = Field(..., description="Who is promoting this stub")
    reason: str = Field(..., description="Why this stub is being promoted to a real case")
    citation_id: Optional[int] = None
    citation_justification: Optional[str] = None


# ── Full-Text Search ─────────────────────────────────────────────────

class SearchHit(BaseModel):
    """A single result from the cross-table full-text search endpoint."""

    hit_type: Literal["case", "document", "source"]
    """Which table this hit came from."""

    case_pk: int
    """Database PK of the parent case (cases.id)."""

    case_ref: str
    """Human-readable case identifier (cases.case_id)."""

    case_name: Optional[str] = None

    title: str
    """case_name for case hits; document_title / source_title for the others."""

    snippet: Optional[str] = None
    """ts_headline excerpt with <mark>…</mark> highlighting (case hits only)."""

    rank: float
    """ts_rank_cd relevance score (higher = more relevant)."""

    # Case-specific optional fields
    court: Optional[str] = None
    filing_date: Optional[date] = None
    case_status: Optional[str] = None

    # Document-specific optional fields
    document_type: Optional[str] = None
    document_date: Optional[date] = None

    # Source-specific optional fields
    source_type: Optional[str] = None
    publication_date: Optional[date] = None

    url: Optional[str] = None

    class Config:
        from_attributes = True


class SearchSuggestion(BaseModel):
    """A Related-Search suggestion derived from tag co-occurrence / similarity."""

    term: str
    """Suggested search term (usually a tag value)."""

    tag_type: Optional[str] = None
    """Tag category, e.g. 'technology', 'jurisdiction'."""

    count: int = 0
    """Number of cases sharing this term with the current result set."""


class SearchOut(BaseModel):
    """Paginated response for /search."""

    query: str
    """The original query string."""

    total: int
    """Approximate total number of matching records across all searched tables."""

    items: List[SearchHit]

    suggestions: List[SearchSuggestion] = []
    """Related-search suggestions (populated when total < 20)."""


# ── Faceted Search ────────────────────────────────────────────────────

class FacetBucket(BaseModel):
    """A single facet value + document count."""
    value: str
    count: int


class FacetsOut(BaseModel):
    """Facet counts for the Cases browser sidebar."""
    courts:       List[FacetBucket] = []
    statuses:     List[FacetBucket] = []
    outcomes:     List[FacetBucket] = []
    filing_years: List[FacetBucket] = []
    circuits:     List[FacetBucket] = []
    states:       List[FacetBucket] = []
    tag_types:    List[FacetBucket] = []


# ── Saved Views ───────────────────────────────────────────────────────

class SavedViewCreate(BaseModel):
    """Payload for creating or replacing a saved filter-preset view."""
    name:        str           = Field(..., max_length=128)
    description: Optional[str] = None
    filters:     dict          = Field(default_factory=dict)
    sort_by:     str           = Field("id",  max_length=64)
    sort_dir:    str           = Field("asc", max_length=4, pattern="^(asc|desc)$")
    columns:     Optional[List[str]] = None


class SavedViewOut(BaseModel):
    """Serialised saved view returned by the API."""
    id:          int
    name:        str
    description: Optional[str]
    filters:     dict
    sort_by:     str
    sort_dir:    str
    columns:     Optional[List[str]]
    created_at:  datetime
    updated_at:  datetime

    class Config:
        from_attributes = True


# ── Legal Citations ───────────────────────────────────────────────────

class LegalCitationCreate(BaseModel):
    """Payload for attaching a legal citation to a case."""
    citation_text: str
    reporter:      Optional[str] = None
    volume:        Optional[int] = None
    page:          Optional[int] = None
    year:          Optional[int] = None


class LegalCitationOut(BaseModel):
    id:            int
    case_id:       int
    citation_text: str
    reporter:      Optional[str] = None
    volume:        Optional[int] = None
    page:          Optional[int] = None
    year:          Optional[int] = None
    created_at:    datetime

    class Config:
        from_attributes = True


# ── Incremental Delta Load ────────────────────────────────────────────

class DeltaRowEntry(BaseModel):
    """One row processed during a delta load."""
    source_file:    str
    table_name:     str
    row_number:     int
    action:         str   # insert | update | skip
    checksum_old:   Optional[str] = None
    checksum_new:   Optional[str] = None
    changed_fields: Optional[dict] = None
    logged_at:      Optional[datetime] = None

    class Config:
        from_attributes = True


class DeltaSummary(BaseModel):
    """Aggregated result of a delta pipeline run."""
    run_id:             str
    total_rows_scanned: int
    inserted:           int
    updated:            int
    skipped:            int
    # Per-file breakdown: {filename: {insert, update, skip}}
    by_file:            dict = Field(default_factory=dict)


# ── Data Versioning / Snapshots ───────────────────────────────────────

class SnapshotCreate(BaseModel):
    """Payload for manually requesting a snapshot."""
    label:       str           = Field(..., max_length=128)
    description: Optional[str] = None


class SnapshotOut(BaseModel):
    """Metadata for a single curated snapshot."""
    id:           int
    run_id:       Optional[str]
    label:        str
    description:  Optional[str]
    taken_at:     datetime
    case_count:   int
    doc_count:    int
    source_count: int
    tag_count:    int
    is_auto:      bool

    class Config:
        from_attributes = True


class CaseDiff(BaseModel):
    """One case entry in a snapshot diff report."""
    case_pk:        int
    case_id:        Optional[str]
    case_name:      Optional[str] = None
    action:         str           # added | removed | changed
    changed_fields: Optional[dict] = None   # {field: {old, new}}


class SnapshotDiffOut(BaseModel):
    """Full diff between two consecutive (or specified) snapshots."""
    snapshot_id:         int
    snapshot_label:      str
    snapshot_taken_at:   Optional[str]
    prev_snapshot_id:    Optional[int]
    prev_snapshot_label: Optional[str]
    added_count:         int
    removed_count:       int
    changed_count:       int
    unchanged_count:     int
    cases:               List[CaseDiff] = []

