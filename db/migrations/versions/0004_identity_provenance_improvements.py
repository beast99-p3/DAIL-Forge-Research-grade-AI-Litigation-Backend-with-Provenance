"""identity, tag governance, pipeline provenance improvements

Changes
-------
- cases:       add legacy_case_number, case_fingerprint
- tags:        add slug, is_official, source
- change_log:  add actor_type, operation, run_id
- NEW TABLE:   pipeline_runs

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── cases: identity fields ────────────────────────────────────────
    op.add_column("cases", sa.Column("legacy_case_number", sa.String(64), nullable=True))
    op.create_index("ix_cases_legacy_case_number", "cases", ["legacy_case_number"])

    op.add_column("cases", sa.Column("case_fingerprint", sa.String(64), nullable=True))
    op.create_index("ix_cases_case_fingerprint", "cases", ["case_fingerprint"])

    # ── tags: governance fields ───────────────────────────────────────
    op.add_column("tags", sa.Column("slug", sa.String(128), nullable=True))
    op.create_index("ix_tags_slug", "tags", ["slug"])

    op.add_column(
        "tags",
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("tags", sa.Column("source", sa.String(128), nullable=True))

    # ── change_log: pipeline provenance fields ────────────────────────
    op.add_column(
        "change_log",
        sa.Column("actor_type", sa.String(16), nullable=False, server_default="human"),
    )
    op.add_column(
        "change_log",
        sa.Column("operation", sa.String(16), nullable=False, server_default="update"),
    )
    op.add_column("change_log", sa.Column("run_id", sa.String(64), nullable=True))
    op.create_index("ix_change_log_run_id", "change_log", ["run_id"])

    # ── pipeline_runs: new table ──────────────────────────────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("data_dir", sa.Text(), nullable=True),
        sa.Column("file_hashes", sa.JSON(), nullable=True),
        sa.Column("raw_counts", sa.JSON(), nullable=True),
        sa.Column("curated_counts", sa.JSON(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_pipeline_runs_run_id", "pipeline_runs", ["run_id"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_run_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_index("ix_change_log_run_id", table_name="change_log")
    op.drop_column("change_log", "run_id")
    op.drop_column("change_log", "operation")
    op.drop_column("change_log", "actor_type")

    op.drop_column("tags", "source")
    op.drop_column("tags", "is_official")
    op.drop_index("ix_tags_slug", table_name="tags")
    op.drop_column("tags", "slug")

    op.drop_index("ix_cases_case_fingerprint", table_name="cases")
    op.drop_column("cases", "case_fingerprint")
    op.drop_index("ix_cases_legacy_case_number", table_name="cases")
    op.drop_column("cases", "legacy_case_number")
