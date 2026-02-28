"""fix raw_schema_field – align schema with ORM model

Migration 0002 created raw_schema_field with a legacy column layout
(table_name, raw) that no longer matches the current ORM model.
This migration drops the stale table and recreates it with the correct
columns: row_number, field_name, data_type, is_unique, label, extra_fields.

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the stale raw_schema_field (created by 0002 with wrong columns)
    # and recreate with the correct schema that matches the ORM model.
    op.drop_table("raw_schema_field")

    op.create_table(
        "raw_schema_field",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_file", sa.String(128), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("field_name", sa.Text(), nullable=True),
        sa.Column("data_type", sa.Text(), nullable=True),
        sa.Column("is_unique", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("extra_fields", sa.JSON(), nullable=True),
    )
    op.create_index("ix_raw_schema_field_source_file", "raw_schema_field", ["source_file"])


def downgrade() -> None:
    op.drop_index("ix_raw_schema_field_source_file", table_name="raw_schema_field")
    op.drop_table("raw_schema_field")

    # Restore the 0002 version
    op.create_table(
        "raw_schema_field",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=True),
        sa.Column("data_type", sa.Text(), nullable=True),
        sa.Column("is_unique", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )
