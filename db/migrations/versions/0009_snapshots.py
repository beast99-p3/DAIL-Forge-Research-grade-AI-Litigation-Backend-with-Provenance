"""Create curated_snapshots and snapshot_cases tables.

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curated_snapshots",
        sa.Column("id",           sa.BigInteger, primary_key=True, autoincrement=True),
        # Links back to the pipeline run that triggered this snapshot (nullable
        # for manually requested snapshots).
        sa.Column("run_id",       sa.String(64),  nullable=True),
        sa.Column("label",        sa.String(128), nullable=False),
        sa.Column("description",  sa.Text,        nullable=True),
        sa.Column("taken_at",     sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("case_count",   sa.Integer,  server_default="0"),
        sa.Column("doc_count",    sa.Integer,  server_default="0"),
        sa.Column("source_count", sa.Integer,  server_default="0"),
        sa.Column("tag_count",    sa.Integer,  server_default="0"),
        # True when this snapshot was taken automatically at end of a pipeline run
        sa.Column("is_auto",      sa.Boolean,  server_default="false"),
    )
    op.create_index("ix_curated_snapshots_taken_at", "curated_snapshots", ["taken_at"])
    op.create_index("ix_curated_snapshots_run_id",   "curated_snapshots", ["run_id"])

    op.create_table(
        "snapshot_cases",
        sa.Column("id",           sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id",  sa.BigInteger,
                  sa.ForeignKey("curated_snapshots.id", ondelete="CASCADE"), nullable=False),
        # Original PK in the live cases table  (not a hard FK – snapshot is a point-in-time copy)
        sa.Column("case_pk",      sa.BigInteger, nullable=False),
        sa.Column("case_id",      sa.String(64)),
        sa.Column("case_name",    sa.Text),
        sa.Column("court",        sa.Text),
        sa.Column("filing_date",  sa.Date),
        sa.Column("closing_date", sa.Date),
        sa.Column("case_status",  sa.String(64)),
        sa.Column("case_outcome", sa.String(128)),
        sa.Column("case_type",    sa.String(128)),
        sa.Column("plaintiff",    sa.Text),
        sa.Column("defendant",    sa.Text),
        sa.Column("judge",        sa.Text),
        sa.Column("summary",      sa.Text),
        sa.Column("is_stub",      sa.Boolean),
        sa.Column("state",        sa.String(8)),
        sa.Column("circuit",      sa.String(16)),
        # [{tag_type, value}] for quick diff without tag table join
        sa.Column("tag_values",   sa.JSON),
        # SHA-256 of all above fields – enables fast changed-case detection
        sa.Column("row_checksum", sa.String(64)),
    )
    op.create_index("ix_snapshot_cases_snapshot_id", "snapshot_cases", ["snapshot_id"])
    op.create_index("ix_snapshot_cases_case_pk",     "snapshot_cases", ["case_pk"])
    op.create_index("ix_snapshot_cases_checksum",    "snapshot_cases", ["row_checksum"])


def downgrade() -> None:
    op.drop_table("snapshot_cases")
    op.drop_table("curated_snapshots")
