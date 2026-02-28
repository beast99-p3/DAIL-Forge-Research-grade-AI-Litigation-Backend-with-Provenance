# DAIL Forge

**Research-grade PostgreSQL backend for the Database of AI Litigation (DAIL)**

DAIL Forge migrates DAIL from low-code spreadsheet exports into a normalised, API-accessible PostgreSQL database with a built-in **provenance ledger** that tracks every curated edit — who changed what, when, why, and based on which source.

---

## Architecture Overview

```
┌──────────────┐      ┌──────────────────────────────────────────┐
│  Excel Files │─────▶│           Pipeline (Python)              │
│  (./data/)   │      │  load_all  →  transform  →  validate    │
└──────────────┘      └──────────┬───────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   PostgreSQL 15        │
                    │                        │
                    │  RAW layer             │
                    │    raw_case            │
                    │    raw_docket          │
                    │    raw_document        │
                    │    raw_secondary_source│
                    │                        │
                    │  CURATED layer         │
                    │    cases ──┬── tags    │
                    │    dockets │  case_tags│
                    │    documents           │
                    │    secondary_sources   │
                    │    case_caption_history│
                    │                        │
                    │  PROVENANCE layer      │
                    │    citations           │
                    │    change_log          │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   FastAPI (port 8000)  │
                    │                        │
                    │  GET  /cases           │◀── Public
                    │  GET  /cases/{id}      │    Research
                    │  GET  /export/cases.csv│    API
                    │                        │
                    │  PATCH /cases/{id}     │◀── Restricted
                    │  POST  /cases/{id}/tags│    Curation
                    │  POST  /citations      │    API (API key)
                    │                        │
                    │  POST /pipeline/load   │◀── Pipeline trigger
                    └────────────────────────┘
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

The pipeline runs in three steps:

| Step | Action | Command |
|------|--------|---------|
| 1 | Excel → RAW tables | Loads every row verbatim. Unmapped columns go into `extra_fields` (JSON). |
| 2 | RAW → CURATED | Parses dates, normalises multi-select fields into `tags` + `case_tags`. |
| 3 | Validation | Checks for duplicates, missing required fields, orphan records. |

Multi-select columns (like `Issue_List`, `Area_List`) are split on `,;|\n` and linked via the normalised `tags` / `case_tags` tables.

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

### 6. Get Single Case
```bash
curl http://localhost:8000/cases/1
```

### 7. CSV Export
```bash
curl -o cases.csv "http://localhost:8000/export/cases.csv?court=federal"
```

### 8. Create a Citation + Edit a Case (curation)
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

### RAW Layer (mirrors Excel 1:1)

| Table | Key Columns | Notes |
|-------|------------|-------|
| `raw_case` | id, row_number, case_id, case_name, court, filing_date, case_status, issue_list, area_list, cause_list, algorithm_list, harm_list, extra_fields | All text; extra_fields = JSON catch-all |
| `raw_docket` | id, row_number, case_id, docket_number, entry_date, entry_text, filed_by, extra_fields | |
| `raw_document` | id, row_number, case_id, document_title, document_type, document_date, url, extra_fields | |
| `raw_secondary_source` | id, row_number, case_id, source_title, source_type, publication_date, author, url, extra_fields | |

### CURATED Layer

| Table | Key Columns | Relationships |
|-------|------------|---------------|
| `cases` | id (PK), case_id (UNIQUE), case_name, court, filing_date, closing_date, case_status, case_outcome, case_type, plaintiff, defendant, judge, summary | → dockets, documents, secondary_sources, case_tags |
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
│   └── routes_pipeline.py      # Pipeline trigger endpoint
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
└── data/
    └── (place .xlsx files here)
```

---

## License

See [LICENSE](LICENSE).
