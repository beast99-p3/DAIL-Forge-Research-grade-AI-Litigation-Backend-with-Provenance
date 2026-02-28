"""initial schema

Revision ID: 0001
Revises: None
Create Date: 2026-02-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── RAW LAYER ────────────────────────────────────────────────────
    op.create_table(
        "raw_case",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("case_id", sa.String(64), index=True),
        sa.Column("case_name", sa.Text),
        sa.Column("court", sa.Text),
        sa.Column("filing_date", sa.Text),
        sa.Column("closing_date", sa.Text),
        sa.Column("case_status", sa.Text),
        sa.Column("case_outcome", sa.Text),
        sa.Column("case_type", sa.Text),
        sa.Column("plaintiff", sa.Text),
        sa.Column("defendant", sa.Text),
        sa.Column("judge", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("issue_list", sa.Text),
        sa.Column("area_list", sa.Text),
        sa.Column("cause_list", sa.Text),
        sa.Column("algorithm_list", sa.Text),
        sa.Column("harm_list", sa.Text),
        sa.Column("extra_fields", sa.JSON),
    )

    op.create_table(
        "raw_docket",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("case_id", sa.String(64), index=True),
        sa.Column("docket_number", sa.Text),
        sa.Column("entry_date", sa.Text),
        sa.Column("entry_text", sa.Text),
        sa.Column("filed_by", sa.Text),
        sa.Column("extra_fields", sa.JSON),
    )

    op.create_table(
        "raw_document",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("case_id", sa.String(64), index=True),
        sa.Column("document_title", sa.Text),
        sa.Column("document_type", sa.Text),
        sa.Column("document_date", sa.Text),
        sa.Column("url", sa.Text),
        sa.Column("extra_fields", sa.JSON),
    )

    op.create_table(
        "raw_secondary_source",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("case_id", sa.String(64), index=True),
        sa.Column("source_title", sa.Text),
        sa.Column("source_type", sa.Text),
        sa.Column("publication_date", sa.Text),
        sa.Column("author", sa.Text),
        sa.Column("url", sa.Text),
        sa.Column("extra_fields", sa.JSON),
    )

    # ── CURATED LAYER ────────────────────────────────────────────────
    op.create_table(
        "cases",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("case_name", sa.Text),
        sa.Column("court", sa.Text, index=True),
        sa.Column("filing_date", sa.Date, index=True),
        sa.Column("closing_date", sa.Date),
        sa.Column("case_status", sa.String(64), index=True),
        sa.Column("case_outcome", sa.String(128)),
        sa.Column("case_type", sa.String(128)),
        sa.Column("plaintiff", sa.Text),
        sa.Column("defendant", sa.Text),
        sa.Column("judge", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tag_type", sa.String(32), nullable=False, index=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.UniqueConstraint("tag_type", "value", name="uq_tag_type_value"),
    )

    op.create_table(
        "case_tags",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.BigInteger, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("case_id", "tag_id", name="uq_case_tag"),
        sa.Index("ix_casetag_case", "case_id"),
        sa.Index("ix_casetag_tag", "tag_id"),
    )

    op.create_table(
        "dockets",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("docket_number", sa.Text),
        sa.Column("entry_date", sa.Date, index=True),
        sa.Column("entry_text", sa.Text),
        sa.Column("filed_by", sa.Text),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_title", sa.Text),
        sa.Column("document_type", sa.String(128)),
        sa.Column("document_date", sa.Date, index=True),
        sa.Column("url", sa.Text),
    )

    op.create_table(
        "secondary_sources",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_title", sa.Text),
        sa.Column("source_type", sa.String(128)),
        sa.Column("publication_date", sa.Date),
        sa.Column("author", sa.Text),
        sa.Column("url", sa.Text),
    )

    op.create_table(
        "case_caption_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_caption", sa.Text),
        sa.Column("new_caption", sa.Text, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("changed_by", sa.String(128)),
        sa.Column("reason", sa.Text),
    )

    # ── PROVENANCE LAYER ─────────────────────────────────────────────
    op.create_table(
        "citations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("accessed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "change_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(64), nullable=False, index=True),
        sa.Column("record_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("field_name", sa.String(128), nullable=False),
        sa.Column("old_value", sa.Text),
        sa.Column("new_value", sa.Text),
        sa.Column("editor_id", sa.String(128), nullable=False, index=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("citation_id", sa.BigInteger, sa.ForeignKey("citations.id", ondelete="SET NULL")),
        sa.Column("citation_justification", sa.Text),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("change_log")
    op.drop_table("citations")
    op.drop_table("case_caption_history")
    op.drop_table("secondary_sources")
    op.drop_table("documents")
    op.drop_table("dockets")
    op.drop_table("case_tags")
    op.drop_table("tags")
    op.drop_table("cases")
    op.drop_table("raw_secondary_source")
    op.drop_table("raw_document")
    op.drop_table("raw_docket")
    op.drop_table("raw_case")
