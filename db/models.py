"""
DAIL Forge – SQLAlchemy ORM models.

Layout
------
RAW layer   – mirrors Excel rows verbatim (raw_case, raw_docket, …)
CURATED layer – normalised research-ready tables
PROVENANCE  – change_log + citations
"""

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Date, DateTime, Boolean,
    ForeignKey, Index, UniqueConstraint, JSON, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Base ─────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ====================================================================
# RAW LAYER – one-to-one mirror of Excel exports
# ====================================================================

class RawCase(Base):
    __tablename__ = "raw_case"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # --- columns discovered from the Case Excel ---
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
    # Catch-all for any extra columns
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON)


class RawDocket(Base):
    __tablename__ = "raw_docket"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    docket_number: Mapped[Optional[str]] = mapped_column(Text)
    entry_date: Mapped[Optional[str]] = mapped_column(Text)
    entry_text: Mapped[Optional[str]] = mapped_column(Text)
    filed_by: Mapped[Optional[str]] = mapped_column(Text)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON)


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


# ====================================================================
# CURATED LAYER
# ====================================================================

class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
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

    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    citation: Mapped[Optional["Citation"]] = relationship()
