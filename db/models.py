"""
DAIL Forge – SQLAlchemy ORM models.

Layout
------
RAW layer   – mirrors Excel rows verbatim; schema-metadata files are stored
              in ``raw_schema_field`` while actual data goes into raw_document
              and raw_secondary_source.
CURATED layer – normalised research-ready tables (cases may be *stubs*
                synthesised from FK references when no case data was exported).
PROVENANCE  – change_log + citations
"""

from datetime import datetime, date
from typing import Any, Optional, List

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Date, DateTime, Boolean,
    ForeignKey, Index, UniqueConstraint, JSON, func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Base ─────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ====================================================================
# RAW LAYER
# ====================================================================

# -- Schema-metadata rows (from Case_Table / Docket_Table) -----------

class RawSchemaField(Base):
    """
    Stores column-definition rows from DAIL schema-metadata files.

    Case_Table.xlsx and Docket_Table.xlsx contain ~36 / ~5 rows
    respectively, each describing a column (Name, DataType, Unique, Label).
    """
    __tablename__ = "raw_schema_field"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    field_name: Mapped[Optional[str]] = mapped_column(Text)
    data_type: Mapped[Optional[str]] = mapped_column(Text)
    is_unique: Mapped[Optional[str]] = mapped_column(Text)
    label: Mapped[Optional[str]] = mapped_column(Text)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON)
    row_checksum: Mapped[Optional[str]]  = mapped_column(String(64), nullable=True, index=True)


# -- Data rows (from Case_Table / Document_Table / Secondary_Source_Coverage_Table)

class RawCase(Base):
    """
    Stores raw case rows from Case_Table.xlsx verbatim.

    All columns are Text so the RAW layer preserves the original values
    exactly as exported.  Multi-select tag columns (issue_list, etc.) are
    split into normalised Tag / CaseTag rows during the transform step.
    """
    __tablename__ = "raw_case"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    case_name: Mapped[Optional[str]] = mapped_column(Text)
    court: Mapped[Optional[str]] = mapped_column(Text)
    filing_date: Mapped[Optional[str]] = mapped_column(Text)
    closing_date: Mapped[Optional[str]] = mapped_column(Text)
    case_status: Mapped[Optional[str]] = mapped_column(Text)
    case_outcome: Mapped[Optional[str]] = mapped_column(Text)
    case_type: Mapped[Optional[str]] = mapped_column(Text)
    plaintiff: Mapped[Optional[str]] = mapped_column(Text)
    defendant: Mapped[Optional[str]] = mapped_column(Text)
    judge: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    issue_list: Mapped[Optional[str]] = mapped_column(Text)
    area_list: Mapped[Optional[str]] = mapped_column(Text)
    cause_list: Mapped[Optional[str]] = mapped_column(Text)
    algorithm_list: Mapped[Optional[str]] = mapped_column(Text)
    harm_list: Mapped[Optional[str]] = mapped_column(Text)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON)
    row_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)


class RawDocument(Base):
    __tablename__ = "raw_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    document_title: Mapped[Optional[str]] = mapped_column(Text)
    document_type: Mapped[Optional[str]] = mapped_column(Text)
    document_date: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON)
    row_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)


class RawSecondarySource(Base):
    __tablename__ = "raw_secondary_source"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    source_title: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(Text)
    publication_date: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON)
    row_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)


class RawDocket(Base):
    """
    Stores raw docket rows from Docket_Table.xlsx verbatim (sheet 0).
    The second sheet ("Field Names, Types") is loaded into raw_schema_field.
    """
    __tablename__ = "raw_docket"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    court: Mapped[Optional[str]] = mapped_column(Text)
    docket_number: Mapped[Optional[str]] = mapped_column(Text)
    entry_date: Mapped[Optional[str]] = mapped_column(Text)
    entry_text: Mapped[Optional[str]] = mapped_column(Text)
    filed_by: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON)
    row_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)


# ====================================================================
# CURATED LAYER
# ====================================================================

class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Original surrogate key from the Excel export.  Stored for traceability but
    # NOT used as the canonical identity (export ordering can change across releases).
    legacy_case_number: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    case_name: Mapped[Optional[str]] = mapped_column(Text)
    court: Mapped[Optional[str]] = mapped_column(Text, index=True)
    filing_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    closing_date: Mapped[Optional[date]] = mapped_column(Date)
    case_status: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    case_outcome: Mapped[Optional[str]] = mapped_column(String(128))
    case_type: Mapped[Optional[str]] = mapped_column(String(128))
    plaintiff: Mapped[Optional[str]] = mapped_column(Text)
    defendant: Mapped[Optional[str]] = mapped_column(Text)
    judge: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)

    # True when the case was synthesised from FK references rather than
    # loaded from a real data file.  Curators should replace stubs with
    # real data when the full Case export becomes available.
    is_stub: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", index=True)
    # SHA-256 fingerprint of the best-known stable identifiers (docket_number,
    # court, caption, filing_date).  Enables safe merge/de-dup across imports.
    case_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # Full-text search vector: weighted tsvector across case_name (A), plaintiff/
    # defendant (B), court (C), summary/status/outcome/judge (D).
    # Populated and maintained by the Postgres trigger added in migration 0006.
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)

    # Geo classification derived from court string (migration 0007 backfill).
    state:   Mapped[Optional[str]] = mapped_column(String(8),  nullable=True, index=True)
    circuit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationships
    tags: Mapped[List["CaseTag"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    dockets: Mapped[List["Docket"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    documents: Mapped[List["Document"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    secondary_sources: Mapped[List["SecondarySource"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    caption_history: Mapped[List["CaseCaptionHistory"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class Tag(Base):
    """Normalised tag values.  tag_type ∈ {issue, area, cause, algorithm, harm}."""
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tag_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    # Machine-stable slug (lowercase, underscored).  Stable across label edits.
    slug: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    # False when the tag came from unmapped/unknown pipeline data —
    # requires curator review before it enters the controlled vocabulary.
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Who created this tag: 'pipeline', 'curation', or any editor_id
    source: Mapped[Optional[str]] = mapped_column(String(128))

    __table_args__ = (
        UniqueConstraint("tag_type", "value", name="uq_tag_type_value"),
    )


class CaseTag(Base):
    """Many-to-many join between cases and tags."""
    __tablename__ = "case_tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    case: Mapped["Case"] = relationship(back_populates="tags")
    tag: Mapped["Tag"] = relationship()

    __table_args__ = (
        UniqueConstraint("case_id", "tag_id", name="uq_case_tag"),
        Index("ix_casetag_case", "case_id"),
        Index("ix_casetag_tag", "tag_id"),
    )


class Docket(Base):
    __tablename__ = "dockets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    docket_number: Mapped[Optional[str]] = mapped_column(Text)
    entry_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    entry_text: Mapped[Optional[str]] = mapped_column(Text)
    filed_by: Mapped[Optional[str]] = mapped_column(Text)

    case: Mapped["Case"] = relationship(back_populates="dockets")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    document_title: Mapped[Optional[str]] = mapped_column(Text)
    document_type: Mapped[Optional[str]] = mapped_column(String(128))
    document_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    url: Mapped[Optional[str]] = mapped_column(Text)

    case: Mapped["Case"] = relationship(back_populates="documents")


class SecondarySource(Base):
    __tablename__ = "secondary_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    source_title: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(String(128))
    publication_date: Mapped[Optional[date]] = mapped_column(Date)
    author: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)

    case: Mapped["Case"] = relationship(back_populates="secondary_sources")


class CaseCaptionHistory(Base):
    """Tracks case-name / caption changes over time."""
    __tablename__ = "case_caption_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    old_caption: Mapped[Optional[str]] = mapped_column(Text)
    new_caption: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    changed_by: Mapped[Optional[str]] = mapped_column(String(128))
    reason: Mapped[Optional[str]] = mapped_column(Text)

    case: Mapped["Case"] = relationship(back_populates="caption_history")


# ====================================================================
# PROVENANCE LAYER
# ====================================================================

class Citation(Base):
    """Authoritative source backing a curated edit."""
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. 'court_filing', 'news', 'docket'
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)         # URL or document ID
    description: Mapped[Optional[str]] = mapped_column(Text)
    accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeLog(Base):
    """
    Provenance ledger: every curated-layer write produces exactly one row.
    Captures WHO changed WHAT, WHEN, WHY, and based on WHICH source.
    """
    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)

    editor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    citation_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("citations.id", ondelete="SET NULL")
    )
    citation_justification: Mapped[Optional[str]] = mapped_column(Text)  # required when citation_id is NULL

    # Pipeline provenance
    actor_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="human"
    )  # 'human' | 'pipeline'
    operation: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="update"
    )  # 'create' | 'update' | 'delete' | 'merge'
    run_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # FK to pipeline_runs.run_id

    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    citation: Mapped[Optional["Citation"]] = relationship()


class PipelineRun(Base):
    """
    Registry of every pipeline execution.

    Enables:
    - Full audit trail of bulk data loads
    - Schema drift detection (compare file_hashes across runs)
    - Linking change_log rows back to the run that created them
    """
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")  # running|success|failed
    data_dir: Mapped[Optional[str]] = mapped_column(Text)
    # {filename: sha256_hex} — used for schema drift detection across runs
    file_hashes: Mapped[Optional[dict]] = mapped_column(JSON)
    raw_counts: Mapped[Optional[dict]] = mapped_column(JSON)
    curated_counts: Mapped[Optional[dict]] = mapped_column(JSON)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[Optional[str]] = mapped_column(Text)


# ====================================================================
# SEARCH EXTENSIONS  (migration 0007)
# ====================================================================

class SavedView(Base):
    """
    A named, persisted combination of filters + sort settings.

    Researchers can save complex searches by name and share them as a URL:
      GET /cases?view=privacy-california-2022
    or fetch the filter dict directly:
      GET /views/privacy-california-2022
    """
    __tablename__ = "saved_views"

    id:          Mapped[int]            = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name:        Mapped[str]            = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]]  = mapped_column(Text)
    # Full filter state: {"court": "S.D.N.Y.", "status": "Open", "fts_query": "privacy", ...}
    filters:     Mapped[Optional[dict]] = mapped_column(JSON, nullable=False, server_default="{}")
    sort_by:     Mapped[str]            = mapped_column(String(64),  nullable=False, server_default="id")
    sort_dir:    Mapped[str]            = mapped_column(String(4),   nullable=False, server_default="asc")
    # Optional ordered list of column IDs to show in table view
    columns:     Mapped[Optional[dict]] = mapped_column(JSON)
    created_at:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseLegalCitation(Base):
    """
    A legal citation string attached to a case record.

    Allows ``GET /cases?cite=123+F.3d+456`` (trigram fuzzy match) and
    exact reporter/volume/page lookups.

    Examples of citation_text values:
      "538 U.S. 343", "123 F.3d 456", "22 Cal. 4th 1153"
    """
    __tablename__ = "case_legal_citations"

    id:            Mapped[int]           = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id:       Mapped[int]           = mapped_column(
        BigInteger, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    citation_text: Mapped[str]           = mapped_column(Text, nullable=False)
    reporter:      Mapped[Optional[str]] = mapped_column(String(32))   # "F.3d", "U.S."
    volume:        Mapped[Optional[int]] = mapped_column(Integer)
    page:          Mapped[Optional[int]] = mapped_column(Integer)
    year:          Mapped[Optional[int]] = mapped_column(Integer)
    created_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["Case"] = relationship()


# ====================================================================
# INCREMENTAL DELTA LOAD  (migration 0008)
# ====================================================================

class RawDeltaLog(Base):
    """
    Per-row provenance log for the incremental / delta load.

    Every time `load_all_raw_delta` runs, one row is written here for
    EACH Excel row processed, recording whether it was:
      'insert'  – brand-new row
      'update'  – row existed but at least one field changed
      'skip'    – row existed and all fields are identical (checksum match)
    """
    __tablename__ = "raw_delta_log"

    id:             Mapped[int]            = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id:         Mapped[str]            = mapped_column(String(64),  nullable=False, index=True)
    source_file:    Mapped[str]            = mapped_column(String(128), nullable=False, index=True)
    table_name:     Mapped[str]            = mapped_column(String(64),  nullable=False)
    row_number:     Mapped[int]            = mapped_column(Integer,     nullable=False)
    raw_row_id:     Mapped[Optional[int]]  = mapped_column(BigInteger,  nullable=True)
    action:         Mapped[str]            = mapped_column(String(16),  nullable=False, index=True)
    checksum_old:   Mapped[Optional[str]]  = mapped_column(String(64))
    checksum_new:   Mapped[Optional[str]]  = mapped_column(String(64))
    # {field: {"old": ..., "new": ...}} – only populated for 'update' actions
    changed_fields: Mapped[Optional[dict]] = mapped_column(JSON)
    logged_at:      Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())


# ====================================================================
# DATA VERSIONING / SNAPSHOTS  (migration 0009)
# ====================================================================

class CuratedSnapshot(Base):
    """
    A point-in-time snapshot of the entire curated (cases) layer.

    Taken automatically at the end of every successful pipeline run, and
    on-demand via `POST /snapshots`.  Enables:
      - Reproducibility: researchers can cite "DAIL as of 2026-01-01"
      - Diff: `GET /snapshots/{id}/diff` shows exactly what changed
      - Rollback reference: compare current state to any past snapshot
    """
    __tablename__ = "curated_snapshots"

    id:           Mapped[int]           = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id:       Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    label:        Mapped[str]           = mapped_column(String(128), nullable=False)
    description:  Mapped[Optional[str]] = mapped_column(Text)
    taken_at:     Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    case_count:   Mapped[int]           = mapped_column(Integer, nullable=False, server_default="0")
    doc_count:    Mapped[int]           = mapped_column(Integer, nullable=False, server_default="0")
    source_count: Mapped[int]           = mapped_column(Integer, nullable=False, server_default="0")
    tag_count:    Mapped[int]           = mapped_column(Integer, nullable=False, server_default="0")
    is_auto:      Mapped[bool]          = mapped_column(Boolean, nullable=False, server_default="false")

    cases: Mapped[List["SnapshotCase"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class SnapshotCase(Base):
    """
    A frozen copy of one Case row (+ its tags) inside a CuratedSnapshot.

    Storing denormalised tag_values JSON avoids a multi-table join when
    computing per-field diffs between snapshots.
    """
    __tablename__ = "snapshot_cases"

    id:           Mapped[int]           = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id:  Mapped[int]           = mapped_column(
        BigInteger, ForeignKey("curated_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Original PK in the live cases table (not a hard FK – this is a frozen copy)
    case_pk:      Mapped[int]           = mapped_column(BigInteger, nullable=False, index=True)
    case_id:      Mapped[Optional[str]] = mapped_column(String(64))
    case_name:    Mapped[Optional[str]] = mapped_column(Text)
    court:        Mapped[Optional[str]] = mapped_column(Text)
    filing_date:  Mapped[Optional[date]]= mapped_column(Date)
    closing_date: Mapped[Optional[date]]= mapped_column(Date)
    case_status:  Mapped[Optional[str]] = mapped_column(String(64))
    case_outcome: Mapped[Optional[str]] = mapped_column(String(128))
    case_type:    Mapped[Optional[str]] = mapped_column(String(128))
    plaintiff:    Mapped[Optional[str]] = mapped_column(Text)
    defendant:    Mapped[Optional[str]] = mapped_column(Text)
    judge:        Mapped[Optional[str]] = mapped_column(Text)
    summary:      Mapped[Optional[str]] = mapped_column(Text)
    is_stub:      Mapped[Optional[bool]]= mapped_column(Boolean)
    state:        Mapped[Optional[str]] = mapped_column(String(8))
    circuit:      Mapped[Optional[str]] = mapped_column(String(16))
    # [{tag_type, value}] – denormalised for diff speed
    tag_values:   Mapped[Optional[list]]= mapped_column(JSON)
    # SHA-256 of all above fields – enables O(n) changed-case detection
    row_checksum: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    snapshot: Mapped["CuratedSnapshot"] = relationship(back_populates="cases")
