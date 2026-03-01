"""Add raw_docket table.

Docket_Table.xlsx has two sheets:
  - Sheet 0: actual docket records  (389 rows)  → raw_docket     (NEW)
  - Sheet 1: field metadata         (5 rows)    → raw_schema_field

Previously the first sheet was mis-loaded as schema metadata.  This
migration adds the raw_docket table so the pipeline can load docket data
correctly.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_docket",
        sa.Column("id",           sa.BigInteger,   primary_key=True, autoincrement=True),
        sa.Column("source_file",  sa.String(128),  nullable=True),
        sa.Column("row_number",   sa.Integer,      nullable=False),
        sa.Column("loaded_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("case_id",      sa.String(64),   nullable=True),
        sa.Column("court",        sa.Text,         nullable=True),
        sa.Column("docket_number",sa.Text,         nullable=True),
        sa.Column("entry_date",   sa.Text,         nullable=True),
        sa.Column("entry_text",   sa.Text,         nullable=True),
        sa.Column("filed_by",     sa.Text,         nullable=True),
        sa.Column("url",          sa.Text,         nullable=True),
        sa.Column("extra_fields", sa.JSON,         nullable=True),
        sa.Column("row_checksum", sa.String(64),   nullable=True),
    )
    op.create_index("ix_raw_docket_source_file",  "raw_docket", ["source_file"])
    op.create_index("ix_raw_docket_case_id",      "raw_docket", ["case_id"])
    op.create_index("ix_raw_docket_row_checksum", "raw_docket", ["row_checksum"])


def downgrade() -> None:
    op.drop_table("raw_docket")
