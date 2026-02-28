"""add is_stub to cases

Adds is_stub column to cases (already handled in 0001 for fresh installs;
this migration is a no-op guard for databases that were initialised before
0001 included is_stub).

NOTE: raw_schema_field is created by migration 0001 with the correct schema.
This migration no longer manages that table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # is_stub is already created in 0001 for fresh installs.
    # This is a no-op guard in case the column is missing on very old DBs.
    conn = op.get_bind()
    col_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='cases' AND column_name='is_stub'"
        )
    ).fetchone()
    if not col_exists:
        op.add_column(
            "cases",
            sa.Column("is_stub", sa.Boolean(), nullable=False, server_default="false"),
        )
        op.create_index("ix_cases_is_stub", "cases", ["is_stub"])


def downgrade() -> None:
    pass
