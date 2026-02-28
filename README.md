# DAIL Forge

**Research-grade PostgreSQL backend for the Database of AI Litigation (DAIL)**

DAIL Forge migrates DAIL from low-code spreadsheet exports into a normalised, API-accessible PostgreSQL database with a built-in **provenance ledger** that tracks every curated edit — who changed what, when, why, and based on which source.

---

## Data Assessment

> **Critical finding**: The four DAIL Excel exports are _not all data files_.

| File | Rows | Type | How we handle it |
|------|------|------|-----------------|
| `Case_Table_*.xlsx` | ~36 | **Schema metadata** – each row defines a column (Name, DataType, Unique, Label) | Parsed into `raw_schema_field` |
| `Docket_Table_*.xlsx` | ~5 | **Schema metadata** – same structure | Parsed into `raw_schema_field` |
| `Document_Table_*.xlsx` | ~863 | **Actual data** – one row per document | Loaded into `raw_document` |
| `Secondary_Source_Coverage_Table_*.xlsx` | ~389 | **Actual data** – one row per source | Loaded into `raw_secondary_source` |

Both data files reference `Case_Number` (values 1–518, ~378 unique) as a foreign key, but **no case-data export exists**. The pipeline solves this by synthesising _stub case records_ from every unique Case_Number found in the data tables.

---

## Architecture Overview

```
┌───────────────────────────┐   ┌──────────────────────────────────────────────────┐
│  Excel Files  (./data/)   │──▶│  Pipeline  v2  (schema-aware)                    │
│                           │   │                                                  │
│  Case_Table.xlsx ─────────│──▶│  1. Detect schema-metadata vs data               │
│   (36 rows = col defs)    │   │     → Schema files → raw_schema_field            │
│                           │   │     → Data files   → raw_document /              │
│  Docket_Table.xlsx ───────│──▶│                      raw_secondary_source        │
│   (5 rows = col defs)     │   │                                                  │
│                           │   │  2. Synthesise stub cases from Case_Number FKs   │
│  Document_Table.xlsx ─────│──▶│     (creates ~378 stub Case records)             │
│   (863 data rows)         │   │                                                  │
│                           │   │  3. Transform raw data → curated tables          │
│  Secondary_Source*.xlsx ──│──▶│                                                  │
│   (389 data rows)         │   │  4. Validate                                     │
└───────────────────────────┘   └──────────┬───────────────────────────────────────┘
                                           │
                                           ▼
                              ┌────────────────────────────┐
                              │   PostgreSQL 15             │
                              │                            │
                              │  ┌─ RAW layer ──────────┐  │
                              │  │  raw_schema_field     │  │
                              │  │  raw_document         │  │
                              │  │  raw_secondary_source │  │
                              │  └───────────────────────┘  │
                              │                            │
                              │  ┌─ CURATED layer ──────┐  │
                              │  │  cases (+ is_stub)    │  │
                              │  │  tags    case_tags    │  │
                              │  │  dockets              │  │
                              │  │  documents            │  │
                              │  │  secondary_sources    │  │
                              │  │  case_caption_history │  │
                              │  └───────────────────────┘  │
                              │                            │
                              │  ┌─ PROVENANCE layer ───┐  │
                              │  │  citations            │  │
                              │  │  change_log           │  │
                              │  └───────────────────────┘  │
                              └────────────┬───────────────┘
                                           │
                                           ▼
                              ┌────────────────────────────┐
                              │   FastAPI (port 8000)      │
                              │                            │
                              │  GET  /cases (?is_stub)    │◀── Public
                              │  GET  /cases/{id}          │    Research
                              │  GET  /export/cases.csv    │    API
                              │                            │
                              │  PATCH /cases/{id}         │◀── Restricted
                              │  POST  /cases/{id}/tags    │    Curation
                              │  POST  /citations          │    API (API key)
                              │                            │
                              │  POST /pipeline/load       │◀── Pipeline trigger
                              └────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose

### 1. Clone & Place Data

```bash
git clone <repo-url> && cd DAIL-Forge
```

Copy the four Excel exports into `./data/`:

```
data/
  Case_Table_2026-Feb-21_1952.xlsx
  Docket_Table_2026-Feb-21_2003.xlsx
  Document_Table_2026-Feb-21_2002.xlsx
  Secondary_Source_Coverage_Table_2026-Feb-21_2058.xlsx
```

### 2. Start Everything

```bash
docker compose up --build
```

This will:
1. Start PostgreSQL 15
2. Run Alembic migrations (create all tables)
3. Start the FastAPI server at **http://localhost:8000**

### 3. Load Data

**Option A – Via API** (while containers are running):

```bash
bash scripts/demo_load.sh
```

**Option B – Direct pipeline** (inside the container):

```bash
docker compose exec api python -m pipeline.load_all
```

### 4. Explore

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## How to Load Data

The pipeline runs in four steps:

| Step | Action | Detail |
|------|--------|--------|
| 1 | **Excel → RAW** | Schema-metadata files (Case_Table, Docket_Table) → `raw_schema_field`. Data files (Document_Table, Secondary_Source) → `raw_document` / `raw_secondary_source`. Unmapped columns go into `extra_fields` (JSON). |
| 2 | **Stub synthesis** | Collects every unique `Case_Number` from data tables and creates stub `cases` records (`is_stub = true`) to satisfy FK constraints. |
| 3 | **RAW → CURATED** | Parses dates, links documents and secondary sources to their stub (or real) cases. |
| 4 | **Validation** | Checks for duplicates, orphan records, stub counts. |

When a real case-data export becomes available, the pipeline can be extended to merge real records, clearing the `is_stub` flag.

---

## Sample curl Commands

### 1. Health Check
```bash
curl http://localhost:8000/health
```

### 2. List Cases (paginated)
```bash
curl "http://localhost:8000/cases?page=1&page_size=10"
```

### 3. Filter by Court
```bash
curl "http://localhost:8000/cases?court=district&page_size=5"
```

### 4. Filter by Tag
```bash
curl "http://localhost:8000/cases?tag_type=issue&tag_value=privacy"
```

### 5. Date Range Filter
```bash
curl "http://localhost:8000/cases?date_from=2023-01-01&date_to=2025-12-31"
```

### 6. Filter Stub vs Real Cases
```bash
# Only stubs
curl "http://localhost:8000/cases?is_stub=true"
# Only real (non-stub) cases
curl "http://localhost:8000/cases?is_stub=false"
```

### 7. Get Single Case
```bash
curl http://localhost:8000/cases/1
```

### 7. CSV Export
```bash
curl -o cases.csv "http://localhost:8000/export/cases.csv?court=federal"
```

### 9. Create a Citation + Edit a Case (curation)
```bash
# Create citation
curl -X POST http://localhost:8000/citations \
  -H "X-API-Key: dail-forge-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"source_type":"court_filing","source_ref":"https://pacer.gov/doc/123"}'

# Update case with provenance
curl -X PATCH http://localhost:8000/cases/1 \
  -H "X-API-Key: dail-forge-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "case_status": "Closed",
    "editor_id": "researcher@uni.edu",
    "reason": "Updated per latest PACER entry",
    "citation_id": 1
  }'
```

---

## How Provenance Works

Every write to the curated layer creates an entry in `change_log`:

| Column | Purpose |
|--------|---------|
| `table_name` | Which table was modified (`cases`, `case_tags`, etc.) |
| `record_id` | PK of the modified record |
| `field_name` | Which column changed |
| `old_value` | Previous value (null for new records) |
| `new_value` | New value |
| `editor_id` | Who made the change |
| `reason` | Why the change was made |
| `citation_id` | FK → `citations` (the authoritative source) |
| `citation_justification` | Free-text justification when no citation exists |
| `changed_at` | Timestamp |

**Enforcement rules:**
- Every `PATCH` / `POST` to curation endpoints **must** include `editor_id` + `reason`.
- At least one of `citation_id` or `citation_justification` must be provided (HTTP 422 otherwise).
- Case-name changes are additionally tracked in `case_caption_history`.

View the ledger:
```bash
curl http://localhost:8000/cases/1/change-log
```

---

## How to Extend Tags Safely

Tags are normalised into two tables:

- `tags` (id, tag_type, value) — unique per type+value
- `case_tags` (case_id, tag_id) — many-to-many link

**To add a new tag type** (e.g. `sector`):
1. No schema change needed — `tag_type` is a free-form string.
2. Add tags via the API:
   ```bash
   curl -X POST http://localhost:8000/cases/1/tags \
     -H "X-API-Key: dail-forge-secret-key-change-me" \
     -H "Content-Type: application/json" \
     -d '{"tag_type":"sector","value":"Healthcare","editor_id":"admin","reason":"New classification","citation_justification":"Internal review"}'
   ```
3. To auto-populate from Excel, add the column pattern to `pipeline/column_map.py` and rerun the pipeline.

---

## Entity-Relationship Diagram

### RAW Layer

| Table | Key Columns | Notes |
|-------|------------|-------|
| `raw_schema_field` | id, source_file, row_number, field_name, data_type, is_unique, label, extra_fields | Parsed from Case_Table / Docket_Table schema-metadata files |
| `raw_document` | id, row_number, case_id, document_title, document_type, document_date, url, extra_fields | 863 rows from Document_Table |
| `raw_secondary_source` | id, row_number, case_id, source_title, source_type, publication_date, author, url, extra_fields | 389 rows from Secondary_Source_Coverage_Table |

### CURATED Layer

| Table | Key Columns | Relationships |
|-------|------------|---------------|
| `cases` | id (PK), case_id (UNIQUE), case_name, court, filing_date, closing_date, case_status, case_outcome, case_type, plaintiff, defendant, judge, summary, **is_stub** | → dockets, documents, secondary_sources, case_tags. **Stubs** are synthesised from FK references |
| `tags` | id (PK), tag_type, value | UNIQUE(tag_type, value) |
| `case_tags` | id (PK), case_id (FK→cases), tag_id (FK→tags) | UNIQUE(case_id, tag_id) |
| `dockets` | id (PK), case_id (FK→cases), docket_number, entry_date, entry_text, filed_by | |
| `documents` | id (PK), case_id (FK→cases), document_title, document_type, document_date, url | |
| `secondary_sources` | id (PK), case_id (FK→cases), source_title, source_type, publication_date, author, url | |
| `case_caption_history` | id (PK), case_id (FK→cases), old_caption, new_caption, changed_at, changed_by, reason | |

### PROVENANCE Layer

| Table | Key Columns | Relationships |
|-------|------------|---------------|
| `citations` | id (PK), source_type, source_ref, description, accessed_at | |
| `change_log` | id (PK), table_name, record_id, field_name, old_value, new_value, editor_id, reason, citation_id (FK→citations), citation_justification, changed_at | |

### Key Indexes

- `cases`: case_id (unique), court, filing_date, case_status
- `case_tags`: (case_id, tag_id) unique; individual indexes on each FK
- `tags`: (tag_type, value) unique
- `change_log`: table_name, record_id, editor_id
- All raw tables: case_id

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://dail:dail_secret@db:5432/dail_forge` | Async DB URL |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://dail:dail_secret@db:5432/dail_forge` | Sync DB URL (pipeline/Alembic) |
| `CURATION_API_KEY` | `dail-forge-secret-key-change-me` | API key for write endpoints |

---

## Project Structure

```
├── docker-compose.yml          # One-command startup
├── Dockerfile                  # Python 3.11 + dependencies
├── requirements.txt
├── alembic.ini                 # Alembic config
├── api/
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Settings (env vars)
│   ├── auth.py                 # API key dependency
│   ├── schemas.py              # Pydantic models
│   ├── routes_research.py      # Public read endpoints
│   ├── routes_curation.py      # Restricted write endpoints
│   ├── routes_pipeline.py      # Pipeline trigger endpoint
│   └── routes_stats.py         # Dashboard stats endpoint
├── db/
│   ├── models.py               # SQLAlchemy ORM models
│   ├── session.py              # Engine and session factories
│   └── migrations/
│       ├── env.py
│       ├── script.py.mako
│       └── versions/
│           └── 0001_initial_schema.py
├── pipeline/
│   ├── load_all.py             # Master entry-point (python -m pipeline.load_all)
│   ├── excel_loader.py         # Excel → RAW tables
│   ├── transform.py            # RAW → CURATED
│   ├── validate.py             # Post-load validation
│   └── column_map.py           # Fuzzy column-name mapper
├── scripts/
│   ├── demo_load.sh            # Load Excel data
│   ├── demo_query.sh           # Example read queries
│   └── demo_edit.sh            # Curation + provenance demo
├── static/
│   └── index.html              # Single-page frontend dashboard
└── data/
    └── (place .xlsx files here)
```

---

## License

See [LICENSE](LICENSE).
