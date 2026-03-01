"""
Research API – public read / filter / export endpoints.

Full-text search (FTS) notes
-----------------------------
Endpoints support two search modes:

* ``keyword``   – legacy ILIKE across case_name, plaintiff, defendant, summary.
                  Simple, always works, case-insensitive substring match.
* ``fts_query`` – PostgreSQL ``websearch_to_tsquery`` across the pre-computed
                  ``cases.search_vector`` GIN index.  Supports:
                    - bare words:           privacy surveillance
                    - implicit AND:         facial recognition  (→ facial & recognition)
                    - explicit OR:          privacy OR surveillance
                    - negation:             privacy NOT employment
                    - phrase search:        "facial recognition"
                  Results are automatically ranked by relevance (ts_rank_cd)
                  when no explicit sort column is requested.

The ``GET /search`` endpoint extends FTS across cases, documents, and secondary
sources in a single call, returning ranked hits with highlighted snippets.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Case, CaseTag, Tag, Docket, Document, SecondarySource, ChangeLog, CaseLegalCitation
from db.session import get_async_session
from api.schemas import (
    CaseOut, CaseListOut, DocketOut, DocumentOut, SecondarySourceOut, TagOut,
    ChangeLogOut, SearchHit, SearchOut, FacetBucket, FacetsOut, SearchSuggestion,
)

router = APIRouter(tags=["Research (public read)"])


# ── Helpers ──────────────────────────────────────────────────────────

# Columns that are safe to sort by
_SORTABLE = {
    "id", "case_id", "case_name", "court", "filing_date",
    "closing_date", "case_status", "case_outcome", "is_stub",
    "created_at", "updated_at",
}


def _case_query(
    tag_type: Optional[str] = None,
    tag_value: Optional[str] = None,
    court: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    keyword: Optional[str] = None,
    fts_query: Optional[str] = None,
    is_stub: Optional[bool] = None,
    state: Optional[str] = None,
    circuit: Optional[str] = None,
    cite: Optional[str] = None,
):
    """
    Build a SELECT for cases with optional filters.

    Tag filters use a JOIN which can produce duplicate rows – we guard
    against that with a DISTINCT on ``cases.id`` so both COUNT and the
    paginated fetch always return one row per case.

    When ``fts_query`` is provided it takes precedence over ``keyword``.
    ``fts_query`` uses PostgreSQL ``websearch_to_tsquery`` against the
    pre-built GIN index on ``cases.search_vector``.

    ``state``   – 2-letter state abbreviation (case-insensitive exact match).
    ``circuit``  – circuit label e.g. '9th' or '2nd'.
    ``cite``     – legal citation fragment; matched via pg_trgm similarity.
    """
    stmt = (
        select(Case)
        .options(selectinload(Case.tags).selectinload(CaseTag.tag))
        .distinct()
    )

    if tag_type or tag_value:
        stmt = stmt.join(Case.tags).join(CaseTag.tag)
        if tag_type and tag_value:
            stmt = stmt.filter(Tag.tag_type == tag_type, Tag.value.ilike(f"%{tag_value}%"))
        elif tag_type:
            stmt = stmt.filter(Tag.tag_type == tag_type)
        else:
            stmt = stmt.filter(Tag.value.ilike(f"%{tag_value}%"))

    if court:
        stmt = stmt.filter(Case.court.ilike(f"%{court}%"))
    if date_from:
        stmt = stmt.filter(Case.filing_date >= date_from)
    if date_to:
        stmt = stmt.filter(Case.filing_date <= date_to)
    if status:
        stmt = stmt.filter(Case.case_status.ilike(f"%{status}%"))
    if outcome:
        stmt = stmt.filter(Case.case_outcome.ilike(f"%{outcome}%"))
    if is_stub is not None:
        stmt = stmt.filter(Case.is_stub == is_stub)

    # Geo filters
    if state:
        stmt = stmt.filter(func.upper(Case.state) == state.upper())
    if circuit:
        stmt = stmt.filter(Case.circuit.ilike(f"%{circuit}%"))

    # Citation filter – trigram similarity join on case_legal_citations
    if cite:
        stmt = (
            stmt
            .join(CaseLegalCitation, CaseLegalCitation.case_id == Case.id)
            .filter(
                func.similarity(CaseLegalCitation.citation_text, cite) > 0.25
            )
        )

    if fts_query:
        # Full-text search via GIN-indexed tsvector (ranked later in callers)
        tsq = func.websearch_to_tsquery("english", fts_query)
        stmt = stmt.filter(Case.search_vector.op("@@")(tsq))
    elif keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.filter(
            or_(
                Case.case_name.ilike(pattern),
                Case.plaintiff.ilike(pattern),
                Case.defendant.ilike(pattern),
                Case.summary.ilike(pattern),
            )
        )

    return stmt


def _count_query(base_stmt):
    """
    Return a COUNT statement from a base Case query.
    Wraps in a subquery so DISTINCT and JOINs are handled correctly.
    """
    return select(func.count()).select_from(base_stmt.subquery())


def _case_to_out(c: Case) -> CaseOut:
    tags = [TagOut(id=ct.tag.id, tag_type=ct.tag.tag_type, value=ct.tag.value) for ct in c.tags]
    return CaseOut(
        id=c.id, case_id=c.case_id, case_name=c.case_name, court=c.court,
        filing_date=c.filing_date, closing_date=c.closing_date,
        case_status=c.case_status, case_outcome=c.case_outcome,
        case_type=c.case_type, plaintiff=c.plaintiff, defendant=c.defendant,
        judge=c.judge, summary=c.summary, is_stub=c.is_stub, tags=tags,
        created_at=c.created_at, updated_at=c.updated_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/cases", response_model=CaseListOut)
async def list_cases(
    session: AsyncSession = Depends(get_async_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort_by: str = Query("id", description="Sort field (ignored when fts_query is set and no explicit sort is requested)"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    tag_type: Optional[str] = None,
    tag_value: Optional[str] = None,
    court: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    keyword: Optional[str] = Query(None, description="Simple substring search across name, parties, summary"),
    fts_query: Optional[str] = Query(
        None,
        description=(
            "Full-text search using PostgreSQL websearch_to_tsquery. "
            "Supports: bare words, AND (default), OR, NOT, \"quoted phrases\". "
            "Results sorted by relevance when no other sort column is chosen. "
            "Example: '\"facial recognition\" AND NOT employment'"
        ),
    ),
    is_stub: Optional[bool] = Query(None, description="Filter by stub status"),
    state: Optional[str] = Query(None, description="2-letter US state abbreviation, e.g. 'CA'"),
    circuit: Optional[str] = Query(None, description="Circuit label, e.g. '9th' or '2nd'"),
    cite: Optional[str] = Query(None, description="Legal citation fragment (trigram fuzzy match), e.g. '538 U.S. 343'"),
):
    base = _case_query(tag_type, tag_value, court, date_from, date_to, status, outcome, keyword, fts_query, is_stub, state, circuit, cite)

    # Total count – uses a clean subquery so JOINs don't inflate the count
    total = (await session.execute(_count_query(base))).scalar_one()

    # Sorting: use relevance rank when fts_query is active and the caller
    # hasn't explicitly requested a different sort column.
    use_fts_rank = bool(fts_query) and sort_by == "id"

    if use_fts_rank:
        tsq = func.websearch_to_tsquery("english", fts_query)
        rank_col = func.ts_rank_cd(Case.search_vector, tsq).label("fts_rank")
        # PostgreSQL DISTINCT requires ORDER BY expressions to appear in the
        # SELECT list.  Add the rank column so ORDER BY fts_rank is valid.
        stmt = (
            base
            .add_columns(rank_col)
            .order_by(rank_col.desc(), Case.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        # Each row is (Case, rank_value) – extract only the ORM object
        cases = [row[0] for row in result.unique().all()]
    else:
        sort_field = sort_by if sort_by in _SORTABLE else "id"
        sort_col = getattr(Case, sort_field)
        order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
        # Always add a stable secondary sort so pagination is deterministic
        stmt = base.order_by(order, Case.id.asc()).offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(stmt)
        cases = result.unique().scalars().all()

    return CaseListOut(
        total=total, page=page, page_size=page_size,
        items=[_case_to_out(c) for c in cases],
    )


# ── Faceted search ───────────────────────────────────────────────────

@router.get("/cases/facets", response_model=FacetsOut, tags=["Research (public read)"])
async def get_case_facets(
    session: AsyncSession = Depends(get_async_session),
    tag_type: Optional[str] = None,
    tag_value: Optional[str] = None,
    court: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    keyword: Optional[str] = None,
    fts_query: Optional[str] = None,
    state: Optional[str] = None,
    circuit: Optional[str] = None,
    cite: Optional[str] = None,
):
    """
    Return facet counts for the current filter context.

    Send the same filters as ``GET /cases`` – the response lists the top-20
    values for each facet dimension (court, status, outcome, year, circuit,
    state, tag_type) together with their document counts.  Use these to build
    a sidebar filter UI.
    """
    base = _case_query(
        tag_type, tag_value, court, date_from, date_to,
        status, outcome, keyword, fts_query, None, state, circuit, cite
    )
    # Wrap base in a subquery so all facet aggregates reference the same filtered set
    sub = base.subquery()

    async def _facet(col_expr, limit: int = 20) -> list[FacetBucket]:
        stmt = (
            select(col_expr.label("v"), func.count().label("c"))
            .select_from(sub)
            .where(col_expr.isnot(None))
            .group_by(col_expr)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        return [FacetBucket(value=str(r.v), count=r.c) for r in rows if r.v]

    # Tag-type facet needs a separate join on the subquery
    tag_sub = (
        select(Tag.tag_type.label("v"), func.count().label("c"))
        .join(CaseTag, CaseTag.tag_id == Tag.id)
        .join(sub, CaseTag.case_id == sub.c.id)
        .group_by(Tag.tag_type)
        .order_by(func.count().desc())
        .limit(20)
    )
    tag_rows = (await session.execute(tag_sub)).all()
    tag_buckets = [FacetBucket(value=str(r.v), count=r.c) for r in tag_rows if r.v]

    # Year facet derived from filing_date
    import sqlalchemy as _sa
    year_stmt = (
        select(
            _sa.cast(func.extract("year", sub.c.filing_date), _sa.Integer).label("v"),
            func.count().label("c"),
        )
        .select_from(sub)
        .where(sub.c.filing_date.isnot(None))
        .group_by("v")
        .order_by(_sa.cast(func.extract("year", sub.c.filing_date), _sa.Integer).desc())
        .limit(20)
    )
    year_rows = (await session.execute(year_stmt)).all()
    year_buckets = [FacetBucket(value=str(r.v), count=r.c) for r in year_rows if r.v]

    return FacetsOut(
        courts=await _facet(sub.c.court),
        statuses=await _facet(sub.c.case_status),
        outcomes=await _facet(sub.c.case_outcome),
        filing_years=year_buckets,
        circuits=await _facet(sub.c.circuit),
        states=await _facet(sub.c.state),
        tag_types=tag_buckets,
    )


@router.get("/cases/{case_id}", response_model=CaseOut)
async def get_case(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(Case).options(
        selectinload(Case.tags).selectinload(CaseTag.tag)
    ).filter(Case.id == case_id)
    result = await session.execute(stmt)
    case = result.unique().scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    return _case_to_out(case)


@router.get("/cases/{case_id}/dockets", response_model=list[DocketOut])
async def get_case_dockets(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(Docket).filter(Docket.case_id == case_id).order_by(Docket.entry_date.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/cases/{case_id}/documents", response_model=list[DocumentOut])
async def get_case_documents(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(Document).filter(Document.case_id == case_id).order_by(Document.document_date.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/cases/{case_id}/secondary-sources", response_model=list[SecondarySourceOut])
async def get_case_secondary_sources(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = select(SecondarySource).filter(SecondarySource.case_id == case_id)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/cases/{case_id}/change-log", response_model=list[ChangeLogOut])
async def get_case_change_log(case_id: int, session: AsyncSession = Depends(get_async_session)):
    stmt = (
        select(ChangeLog)
        .filter(ChangeLog.table_name == "cases", ChangeLog.record_id == case_id)
        .order_by(ChangeLog.changed_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# ── CSV export ───────────────────────────────────────────────────────

@router.get("/export/cases.csv")
async def export_cases_csv(
    session: AsyncSession = Depends(get_async_session),
    tag_type: Optional[str] = None,
    tag_value: Optional[str] = None,
    court: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    keyword: Optional[str] = None,
    fts_query: Optional[str] = None,
    is_stub: Optional[bool] = Query(None, description="Filter by stub status"),
    state: Optional[str] = Query(None, description="2-letter US state abbreviation"),
    circuit: Optional[str] = Query(None, description="Circuit label"),
    cite: Optional[str] = Query(None, description="Legal citation fragment"),
):
    stmt = _case_query(tag_type, tag_value, court, date_from, date_to, status, outcome, keyword, fts_query, is_stub, state, circuit, cite)
    if fts_query:
        tsq = func.websearch_to_tsquery("english", fts_query)
        stmt = stmt.order_by(func.ts_rank_cd(Case.search_vector, tsq).desc())
    else:
        stmt = stmt.order_by(Case.filing_date.desc())
    result = await session.execute(stmt)
    cases = result.unique().scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = [
        "id", "case_id", "case_name", "court", "filing_date", "closing_date",
        "case_status", "case_outcome", "case_type", "plaintiff", "defendant",
        "judge", "summary", "is_stub", "tags",
    ]
    writer.writerow(header)

    for c in cases:
        tags_str = "; ".join(f"{ct.tag.tag_type}:{ct.tag.value}" for ct in c.tags)
        writer.writerow([
            c.id, c.case_id, c.case_name, c.court, c.filing_date, c.closing_date,
            c.case_status, c.case_outcome, c.case_type, c.plaintiff, c.defendant,
            c.judge, c.summary, c.is_stub, tags_str,
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cases.csv"},
    )


# ── Cross-table full-text search ─────────────────────────────────────

@router.get("/search", response_model=SearchOut, tags=["Research (public read)"])
async def full_text_search(
    q: str = Query(
        ...,
        min_length=2,
        description=(
            "Full-text query understood by PostgreSQL websearch_to_tsquery. "
            "Examples: 'privacy', '\"facial recognition\" AND NOT employment', "
            "'privacy OR surveillance', 'generative AI'"
        ),
    ),
    search_in: str = Query(
        "all",
        description="Scope: 'all' | 'cases' | 'documents' | 'sources'",
        pattern="^(all|cases|documents|sources)$",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Cross-table full-text search across cases, court documents, and secondary sources.

    Returns a ranked, de-duplicated list of ``SearchHit`` objects sorted by
    PostgreSQL ``ts_rank_cd`` relevance score.  Case hits include a
    ``ts_headline`` snippet with ``<mark>`` highlights.

    Filtering by court, date, status, etc. can be done afterwards via
    ``GET /cases?fts_query=…&court=…``.
    """
    tsq = func.websearch_to_tsquery("english", q)
    items: list[SearchHit] = []
    total = 0

    # ── Case hits (use pre-built GIN index) ─────────────────────────
    if search_in in ("all", "cases"):
        # Count
        c_count = (
            await session.execute(
                select(func.count(Case.id)).where(
                    Case.search_vector.op("@@")(tsq),
                )
            )
        ).scalar_one()
        total += c_count

        # Ranked fetch with ts_headline snippet
        rank_col = func.ts_rank_cd(Case.search_vector, tsq).label("rank")
        snippet_col = func.ts_headline(
            "english",
            # Prefer summary for highlight; fall back to case_name
            func.coalesce(Case.summary, Case.case_name, ""),
            tsq,
            "MaxWords=20,MinWords=5,StartSel=<mark>,StopSel=</mark>,FragmentDelimiter=…",
        ).label("snippet")

        rows = (
            await session.execute(
                select(Case, rank_col, snippet_col)
                .where(Case.search_vector.op("@@")(tsq))
                .order_by(rank_col.desc())
                .offset((page - 1) * page_size if search_in == "cases" else 0)
                .limit(page_size if search_in == "cases" else max(1, page_size // 2))
            )
        ).all()

        for case, rank, snippet in rows:
            items.append(
                SearchHit(
                    hit_type="case",
                    case_pk=case.id,
                    case_ref=case.case_id,
                    case_name=case.case_name,
                    title=case.case_name or case.case_id,
                    snippet=snippet,
                    rank=float(rank),
                    court=case.court,
                    filing_date=case.filing_date,
                    case_status=case.case_status,
                )
            )

    # ── Document hits (on-the-fly tsvector on document_title) ────────
    if search_in in ("all", "documents"):
        doc_vec = func.to_tsvector("english", func.coalesce(Document.document_title, ""))

        d_count = (
            await session.execute(
                select(func.count(Document.id)).where(doc_vec.op("@@")(tsq))
            )
        ).scalar_one()
        total += d_count

        rank_col = func.ts_rank_cd(doc_vec, tsq).label("rank")
        rows = (
            await session.execute(
                select(
                    Document,
                    Case.case_id.label("case_ref"),
                    Case.case_name.label("case_name_val"),
                    rank_col,
                )
                .join(Case, Document.case_id == Case.id)
                .where(doc_vec.op("@@")(tsq))
                .order_by(rank_col.desc())
                .offset((page - 1) * page_size if search_in == "documents" else 0)
                .limit(page_size if search_in == "documents" else max(1, page_size // 3))
            )
        ).all()

        for doc, case_ref, case_name_val, rank in rows:
            items.append(
                SearchHit(
                    hit_type="document",
                    case_pk=doc.case_id,
                    case_ref=case_ref,
                    case_name=case_name_val,
                    title=doc.document_title or "Untitled Document",
                    snippet=None,
                    rank=float(rank),
                    document_type=doc.document_type,
                    document_date=doc.document_date,
                    url=doc.url,
                )
            )

    # ── Secondary-source hits ────────────────────────────────────────
    if search_in in ("all", "sources"):
        src_vec = func.to_tsvector(
            "english",
            func.coalesce(SecondarySource.source_title, ""),
        )

        s_count = (
            await session.execute(
                select(func.count(SecondarySource.id)).where(src_vec.op("@@")(tsq))
            )
        ).scalar_one()
        total += s_count

        rank_col = func.ts_rank_cd(src_vec, tsq).label("rank")
        rows = (
            await session.execute(
                select(
                    SecondarySource,
                    Case.case_id.label("case_ref"),
                    Case.case_name.label("case_name_val"),
                    rank_col,
                )
                .join(Case, SecondarySource.case_id == Case.id)
                .where(src_vec.op("@@")(tsq))
                .order_by(rank_col.desc())
                .offset((page - 1) * page_size if search_in == "sources" else 0)
                .limit(page_size if search_in == "sources" else max(1, page_size // 3))
            )
        ).all()

        for src, case_ref, case_name_val, rank in rows:
            items.append(
                SearchHit(
                    hit_type="source",
                    case_pk=src.case_id,
                    case_ref=case_ref,
                    case_name=case_name_val,
                    title=src.source_title or "Untitled Source",
                    snippet=None,
                    rank=float(rank),
                    source_type=src.source_type,
                    publication_date=src.publication_date,
                    url=src.url,
                )
            )

    # Merge and re-sort by rank when searching all tables at once
    if search_in == "all":
        items.sort(key=lambda h: h.rank, reverse=True)
        items = items[:page_size]

    # ── Related-search suggestions (populated when results are sparse) ──
    suggestions: list[SearchSuggestion] = []
    if total < 20 and q.strip():
        # Use pg_trgm similarity to suggest tag values close to the query words
        try:
            # ts_stat gives per-lexeme stats from the GIN index; for suggestions
            # we instead query tag values by substring + similarity.
            words = [w.strip('"') for w in q.split() if len(w.strip('"')) >= 3]
            if words:
                first_word = words[0]
                sug_stmt = (
                    select(
                        Tag.value.label("term"),
                        Tag.tag_type,
                        func.count(CaseTag.case_id).label("cnt"),
                    )
                    .join(CaseTag, CaseTag.tag_id == Tag.id)
                    .where(func.similarity(Tag.value, first_word) > 0.2)
                    .group_by(Tag.value, Tag.tag_type)
                    .order_by(func.count(CaseTag.case_id).desc())
                    .limit(6)
                )
                sug_rows = (await session.execute(sug_stmt)).all()
                suggestions = [
                    SearchSuggestion(term=r.term, tag_type=r.tag_type, count=r.cnt)
                    for r in sug_rows
                ]
        except Exception:
            pass  # suggestions are best-effort; never block the response

    return SearchOut(query=q, total=total, items=items, suggestions=suggestions)
