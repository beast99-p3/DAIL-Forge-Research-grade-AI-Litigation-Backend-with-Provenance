"""Add full-text search vector to cases table.

Adds a weighted ``tsvector`` column (search_vector) to the ``cases`` table,
creates a GIN index for fast FTS queries, and installs a BEFORE INSERT/UPDATE
trigger so the column is kept in sync automatically.

Weights:
  A – case_name         (highest relevance)
  B – plaintiff, defendant
  C – court
  D – summary, case_status, case_outcome, case_type, judge

Supports PostgreSQL ``websearch_to_tsquery`` syntax, which understands:
  - bare words          →  privacy
  - AND (default)       →  facial recognition
  - explicit OR         →  privacy OR surveillance
  - negation            →  privacy NOT employment
  - phrase search       →  "facial recognition"

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# --------------------------------------------------------------------
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None
# --------------------------------------------------------------------


def upgrade() -> None:
    # 1. Add the search_vector column ---------------------------------
    op.add_column(
        "cases",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )

    # 2. GIN index for fast FTS queries ------------------------------
    op.create_index(
        "ix_cases_search_vector",
        "cases",
        ["search_vector"],
        postgresql_using="gin",
    )

    # 3. Trigger function: recomputes search_vector on every write ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cases_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.case_name,    '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.plaintiff,    '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.defendant,    '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.court,        '')), 'C') ||
                setweight(to_tsvector('english', coalesce(NEW.summary,      '')), 'D') ||
                setweight(to_tsvector('english', coalesce(NEW.case_status,  '')), 'D') ||
                setweight(to_tsvector('english', coalesce(NEW.case_outcome, '')), 'D') ||
                setweight(to_tsvector('english', coalesce(NEW.case_type,    '')), 'D') ||
                setweight(to_tsvector('english', coalesce(NEW.judge,        '')), 'D');
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )

    # 4. Attach trigger to cases table --------------------------------
    op.execute(
        """
        CREATE TRIGGER trig_cases_search_vector
        BEFORE INSERT OR UPDATE ON cases
        FOR EACH ROW EXECUTE FUNCTION cases_search_vector_update();
        """
    )

    # 5. Backfill existing rows ---------------------------------------
    op.execute(
        """
        UPDATE cases
        SET search_vector =
            setweight(to_tsvector('english', coalesce(case_name,    '')), 'A') ||
            setweight(to_tsvector('english', coalesce(plaintiff,    '')), 'B') ||
            setweight(to_tsvector('english', coalesce(defendant,    '')), 'B') ||
            setweight(to_tsvector('english', coalesce(court,        '')), 'C') ||
            setweight(to_tsvector('english', coalesce(summary,      '')), 'D') ||
            setweight(to_tsvector('english', coalesce(case_status,  '')), 'D') ||
            setweight(to_tsvector('english', coalesce(case_outcome, '')), 'D') ||
            setweight(to_tsvector('english', coalesce(case_type,    '')), 'D') ||
            setweight(to_tsvector('english', coalesce(judge,        '')), 'D');
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_cases_search_vector ON cases")
    op.execute("DROP FUNCTION IF EXISTS cases_search_vector_update()")
    op.drop_index("ix_cases_search_vector", table_name="cases")
    op.drop_column("cases", "search_vector")
