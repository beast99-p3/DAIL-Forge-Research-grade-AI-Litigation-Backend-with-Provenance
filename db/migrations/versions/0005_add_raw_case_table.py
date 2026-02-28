"""add raw_case table for actual case data

This migration adds the raw_case table to store actual case data from
Case_Table.xlsx, which contains real case records rather than schema metadata.

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_case",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("case_id", sa.String(64), index=True),
        sa.Column("case_name", sa.Text()),
        sa.Column("court", sa.Text()),
        sa.Column("filing_date", sa.Text()),
        sa.Column("closing_date", sa.Text()),
        sa.Column("case_status", sa.Text()),
        sa.Column("case_outcome", sa.Text()),
        sa.Column("case_type", sa.Text()),
        sa.Column("plaintiff", sa.Text()),
        sa.Column("defendant", sa.Text()),
        sa.Column("judge", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("issue_list", sa.Text()),
        sa.Column("area_list", sa.Text()),
        sa.Column("cause_list", sa.Text()),
        sa.Column("algorithm_list", sa.Text()),
        sa.Column("harm_list", sa.Text()),
        sa.Column("extra_fields", sa.JSON()),
    )


def downgrade() -> None:
    op.drop_table("raw_case")
