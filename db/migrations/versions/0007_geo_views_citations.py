"""
Add geo columns, saved_views, and case_legal_citations tables.

Changes
-------
1. Enable pg_trgm extension (for similarity-based Related Searches and
   citation fuzzy matching).
2. Add ``state`` (VARCHAR 8) and ``circuit`` (VARCHAR 16) to ``cases``.
   Backfill existing rows from ``court`` text via an inline PL/pgSQL block
   using the same court→geo mapping as pipeline/geo_map.py.
3. Create ``saved_views`` table (filter presets stored as JSONB).
4. Create ``case_legal_citations`` table with a pg_trgm GIN index so
   ``GET /cases?cite=123+F.3d+456`` can fuzzy-match citation strings.

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. pg_trgm extension ────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── 2. Geo columns on cases ─────────────────────────────────────
    op.add_column("cases", sa.Column("state",   sa.String(8),  nullable=True))
    op.add_column("cases", sa.Column("circuit", sa.String(16), nullable=True))
    op.create_index("ix_cases_state",   "cases", ["state"])
    op.create_index("ix_cases_circuit", "cases", ["circuit"])

    # Backfill state / circuit from court text with a lookup block.
    # Uses a VALUES table for portability (no Python in pure-SQL migration).
    op.execute(
        """
        DO $$
        DECLARE
            mapping TEXT[][] := ARRAY[
                -- 2nd Circuit
                ARRAY['s.d.n.y.',  'NY','2nd'], ARRAY['e.d.n.y.',  'NY','2nd'],
                ARRAY['n.d.n.y.',  'NY','2nd'], ARRAY['w.d.n.y.',  'NY','2nd'],
                ARRAY['d. conn.',  'CT','2nd'], ARRAY['d. vt.',    'VT','2nd'],
                -- 3rd Circuit
                ARRAY['e.d. pa.',  'PA','3rd'], ARRAY['m.d. pa.',  'PA','3rd'],
                ARRAY['w.d. pa.',  'PA','3rd'], ARRAY['d. n.j.',   'NJ','3rd'],
                ARRAY['d. del.',   'DE','3rd'],
                -- 4th Circuit
                ARRAY['d. md.',    'MD','4th'], ARRAY['e.d. va.',  'VA','4th'],
                ARRAY['w.d. va.',  'VA','4th'], ARRAY['d.s.c.',    'SC','4th'],
                ARRAY['e.d.n.c.', 'NC','4th'], ARRAY['m.d.n.c.', 'NC','4th'],
                ARRAY['w.d.n.c.', 'NC','4th'],
                -- 5th Circuit
                ARRAY['n.d. tex.','TX','5th'], ARRAY['s.d. tex.','TX','5th'],
                ARRAY['e.d. tex.','TX','5th'], ARRAY['w.d. tex.','TX','5th'],
                ARRAY['e.d. la.', 'LA','5th'], ARRAY['w.d. la.', 'LA','5th'],
                ARRAY['n.d. miss.','MS','5th'],ARRAY['s.d. miss.','MS','5th'],
                -- 6th Circuit
                ARRAY['n.d. ohio','OH','6th'], ARRAY['s.d. ohio','OH','6th'],
                ARRAY['e.d. mich.','MI','6th'],ARRAY['w.d. mich.','MI','6th'],
                ARRAY['e.d. tenn.','TN','6th'],ARRAY['m.d. tenn.','TN','6th'],
                ARRAY['w.d. tenn.','TN','6th'],ARRAY['e.d. ky.', 'KY','6th'],
                ARRAY['w.d. ky.', 'KY','6th'],
                -- 7th Circuit
                ARRAY['n.d. ill.','IL','7th'], ARRAY['c.d. ill.','IL','7th'],
                ARRAY['s.d. ill.','IL','7th'], ARRAY['n.d. ind.','IN','7th'],
                ARRAY['s.d. ind.','IN','7th'], ARRAY['e.d. wis.','WI','7th'],
                ARRAY['w.d. wis.','WI','7th'],
                -- 8th Circuit
                ARRAY['e.d. mo.', 'MO','8th'], ARRAY['w.d. mo.', 'MO','8th'],
                ARRAY['d. minn.', 'MN','8th'], ARRAY['d. neb.',  'NE','8th'],
                ARRAY['d. iowa',  'IA','8th'],  ARRAY['d.n.d.',  'ND','8th'],
                ARRAY['d.s.d.',   'SD','8th'],
                -- 9th Circuit
                ARRAY['n.d. cal.','CA','9th'], ARRAY['s.d. cal.','CA','9th'],
                ARRAY['c.d. cal.','CA','9th'], ARRAY['e.d. cal.','CA','9th'],
                ARRAY['d. ariz.', 'AZ','9th'], ARRAY['d. nev.',  'NV','9th'],
                ARRAY['d. or.',   'OR','9th'], ARRAY['w.d. wash.','WA','9th'],
                ARRAY['e.d. wash.','WA','9th'],ARRAY['d. mont.', 'MT','9th'],
                ARRAY['d. idaho', 'ID','9th'], ARRAY['d. alaska','AK','9th'],
                ARRAY['d. haw.',  'HI','9th'],
                -- 10th Circuit
                ARRAY['d. colo.', 'CO','10th'], ARRAY['d. kan.',  'KS','10th'],
                ARRAY['d.n.m.',   'NM','10th'], ARRAY['d. utah',  'UT','10th'],
                ARRAY['d. wyo.',  'WY','10th'],
                -- 11th Circuit
                ARRAY['n.d. ala.','AL','11th'],ARRAY['m.d. ala.','AL','11th'],
                ARRAY['s.d. ala.','AL','11th'],ARRAY['n.d. fla.','FL','11th'],
                ARRAY['m.d. fla.','FL','11th'],ARRAY['s.d. fla.','FL','11th'],
                ARRAY['n.d. ga.', 'GA','11th'],ARRAY['m.d. ga.', 'GA','11th'],
                ARRAY['s.d. ga.', 'GA','11th'],
                -- DC Circuit
                ARRAY['d.d.c.',   'DC','D.C.'], ARRAY['d.c. cir.','DC','D.C.']
            ];
            row TEXT[];
        BEGIN
            FOREACH row SLICE 1 IN ARRAY mapping LOOP
                UPDATE cases
                SET
                    state   = COALESCE(state,   NULLIF(row[2], '')),
                    circuit = COALESCE(circuit, NULLIF(row[3], ''))
                WHERE lower(court) LIKE '%' || row[1] || '%'
                AND (state IS NULL OR circuit IS NULL);
            END LOOP;

            -- Circuit-number-only rows (Circuit Courts of Appeals)
            UPDATE cases SET circuit = '2nd'  WHERE circuit IS NULL AND lower(court) ~ '\\m2d\\s+cir|2nd\\s+cir';
            UPDATE cases SET circuit = '3rd'  WHERE circuit IS NULL AND lower(court) ~ '\\m3d\\s+cir|3rd\\s+cir';
            UPDATE cases SET circuit = '4th'  WHERE circuit IS NULL AND lower(court) ~ '\\m4th\\s+cir';
            UPDATE cases SET circuit = '5th'  WHERE circuit IS NULL AND lower(court) ~ '\\m5th\\s+cir';
            UPDATE cases SET circuit = '6th'  WHERE circuit IS NULL AND lower(court) ~ '\\m6th\\s+cir';
            UPDATE cases SET circuit = '7th'  WHERE circuit IS NULL AND lower(court) ~ '\\m7th\\s+cir';
            UPDATE cases SET circuit = '8th'  WHERE circuit IS NULL AND lower(court) ~ '\\m8th\\s+cir';
            UPDATE cases SET circuit = '9th'  WHERE circuit IS NULL AND lower(court) ~ '\\m9th\\s+cir';
            UPDATE cases SET circuit = '10th' WHERE circuit IS NULL AND lower(court) ~ '\\m10th\\s+cir';
            UPDATE cases SET circuit = '11th' WHERE circuit IS NULL AND lower(court) ~ '\\m11th\\s+cir';
            UPDATE cases SET circuit = 'D.C.' WHERE circuit IS NULL AND lower(court) ~ 'd\\.c\\.\\s+cir';
        END $$;
        """
    )

    # ── 3. saved_views ──────────────────────────────────────────────
    op.create_table(
        "saved_views",
        sa.Column("id",          sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name",        sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text,        nullable=True),
        # Full filter state as JSONB
        sa.Column("filters",     sa.JSON,  nullable=False, server_default="{}"),
        sa.Column("sort_by",     sa.String(64),  nullable=False, server_default="id"),
        sa.Column("sort_dir",    sa.String(4),   nullable=False, server_default="asc"),
        # Optional ordered list of column names to show
        sa.Column("columns",     sa.JSON,  nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_saved_views_name", "saved_views", ["name"])

    # ── 4. case_legal_citations ─────────────────────────────────────
    op.create_table(
        "case_legal_citations",
        sa.Column("id",          sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id",     sa.BigInteger,
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        # Raw citation string: "123 F.3d 456" or "538 U.S. 343"
        sa.Column("citation_text",       sa.Text, nullable=False),
        # Parsed components (nullable – may be incomplete)
        sa.Column("reporter",    sa.String(32),  nullable=True),  # "F.3d", "U.S."
        sa.Column("volume",      sa.Integer,     nullable=True),
        sa.Column("page",        sa.Integer,     nullable=True),
        sa.Column("year",        sa.Integer,     nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_case_legal_citations_case_id", "case_legal_citations", ["case_id"])
    # Trigram index for fuzzy citation search
    op.execute(
        """
        CREATE INDEX ix_case_legal_citations_trgm
        ON case_legal_citations
        USING gin (citation_text gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_case_legal_citations_trgm")
    op.drop_table("case_legal_citations")
    op.drop_table("saved_views")
    op.drop_index("ix_cases_circuit", table_name="cases")
    op.drop_index("ix_cases_state",   table_name="cases")
    op.drop_column("cases", "circuit")
    op.drop_column("cases", "state")
