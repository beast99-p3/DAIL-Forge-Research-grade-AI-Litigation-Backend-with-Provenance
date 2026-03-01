"""Add row_checksum to RAW tables and create raw_delta_log.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── row_checksum column on every RAW table ─────────────────────
    for tbl in ("raw_case", "raw_document", "raw_secondary_source", "raw_schema_field"):
        op.add_column(tbl, sa.Column("row_checksum", sa.String(64), nullable=True))
        op.create_index(f"ix_{tbl}_checksum", tbl, ["row_checksum"])

    # ── Per-row provenance log ──────────────────────────────────────
    op.create_table(
        "raw_delta_log",
        sa.Column("id",             sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id",         sa.String(64),  nullable=False),
        sa.Column("source_file",    sa.String(128), nullable=False),
        sa.Column("table_name",     sa.String(64),  nullable=False),
        sa.Column("row_number",     sa.Integer,     nullable=False),
        # FK to the raw row itself (nullable – rows we skip never write here)
        sa.Column("raw_row_id",     sa.BigInteger,  nullable=True),
        # insert | update | skip | delete
        sa.Column("action",         sa.String(16),  nullable=False),
        sa.Column("checksum_old",   sa.String(64),  nullable=True),
        sa.Column("checksum_new",   sa.String(64),  nullable=True),
        # {field: {old, new}} – only populated for update actions
        sa.Column("changed_fields", sa.JSON,         nullable=True),
        sa.Column("logged_at",      sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_raw_delta_log_run_id",     "raw_delta_log", ["run_id"])
    op.create_index("ix_raw_delta_log_source_file","raw_delta_log", ["source_file"])
    op.create_index("ix_raw_delta_log_action",     "raw_delta_log", ["action"])


def downgrade() -> None:
    op.drop_table("raw_delta_log")
    for tbl in ("raw_case", "raw_document", "raw_secondary_source", "raw_schema_field"):
        op.drop_index(f"ix_{tbl}_checksum", tbl)
        op.drop_column(tbl, "row_checksum")
