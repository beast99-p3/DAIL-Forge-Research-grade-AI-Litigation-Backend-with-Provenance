#!/usr/bin/env python3
"""
Fix case data quality issues.

Problems:
  - The "court" field in raw_document extra_fields contains document
    descriptions ("Complaint", "Motion to Dismiss"), NOT actual court names.
    The enrichment step mapped these garbage values into Case.court.
  - Most cases have placeholder names like "[Stub] Case #X" or
    "AI Litigation Case #X".

Fixes:
  1. Extract real court names from CourtListener URLs in documents
     (gov.uscourts.XXX patterns → federal court name lookup).
  2. Extract better case names from secondary source titles (often
     contain "Party v. Party" patterns or descriptive case names).
  3. Clear garbage court values that are actually document descriptions.
  4. Extract citations from raw_document extra_fields cite_or_reference.
  5. Re-mark cases that still lack meaningful data as stubs.
"""

import os, sys, re, logging
from datetime import date

# Allow import from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from db.models import Case, Document, SecondarySource, RawDocument

# ── Connection ───────────────────────────────────────────────────────
DB_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://dail:dail_secret@localhost:5434/dail_forge",
)
engine = create_engine(DB_URL, echo=False)
SessionLocal = sessionmaker(engine)

# ── Federal court code → name mapping ────────────────────────────────
# Based on PACER court codes found in CourtListener URLs
# e.g., gov.uscourts.cacd.12345 → "cacd" → Central District of California
COURT_CODE_MAP = {
    # District Courts
    "akd": "U.S. District Court for the District of Alaska",
    "ald": "U.S. District Court for the District of Alabama",
    "almd": "U.S. District Court for the Middle District of Alabama",
    "alnd": "U.S. District Court for the Northern District of Alabama",
    "alsd": "U.S. District Court for the Southern District of Alabama",
    "ared": "U.S. District Court for the Eastern District of Arkansas",
    "arwd": "U.S. District Court for the Western District of Arkansas",
    "azd": "U.S. District Court for the District of Arizona",
    "cacd": "U.S. District Court for the Central District of California",
    "caed": "U.S. District Court for the Eastern District of California",
    "cand": "U.S. District Court for the Northern District of California",
    "casd": "U.S. District Court for the Southern District of California",
    "cod": "U.S. District Court for the District of Colorado",
    "ctd": "U.S. District Court for the District of Connecticut",
    "dcd": "U.S. District Court for the District of Columbia",
    "ded": "U.S. District Court for the District of Delaware",
    "flmd": "U.S. District Court for the Middle District of Florida",
    "flnd": "U.S. District Court for the Northern District of Florida",
    "flsd": "U.S. District Court for the Southern District of Florida",
    "gamd": "U.S. District Court for the Middle District of Georgia",
    "gand": "U.S. District Court for the Northern District of Georgia",
    "gasd": "U.S. District Court for the Southern District of Georgia",
    "hid": "U.S. District Court for the District of Hawaii",
    "iasd": "U.S. District Court for the Southern District of Iowa",
    "iand": "U.S. District Court for the Northern District of Iowa",
    "idd": "U.S. District Court for the District of Idaho",
    "ilcd": "U.S. District Court for the Central District of Illinois",
    "ilnd": "U.S. District Court for the Northern District of Illinois",
    "ilsd": "U.S. District Court for the Southern District of Illinois",
    "innd": "U.S. District Court for the Northern District of Indiana",
    "insd": "U.S. District Court for the Southern District of Indiana",
    "ksd": "U.S. District Court for the District of Kansas",
    "kyed": "U.S. District Court for the Eastern District of Kentucky",
    "kywd": "U.S. District Court for the Western District of Kentucky",
    "laed": "U.S. District Court for the Eastern District of Louisiana",
    "lamd": "U.S. District Court for the Middle District of Louisiana",
    "lawd": "U.S. District Court for the Western District of Louisiana",
    "mad": "U.S. District Court for the District of Massachusetts",
    "mdd": "U.S. District Court for the District of Maryland",
    "med": "U.S. District Court for the District of Maine",
    "mied": "U.S. District Court for the Eastern District of Michigan",
    "miwd": "U.S. District Court for the Western District of Michigan",
    "mnd": "U.S. District Court for the District of Minnesota",
    "moed": "U.S. District Court for the Eastern District of Missouri",
    "mowd": "U.S. District Court for the Western District of Missouri",
    "msnd": "U.S. District Court for the Northern District of Mississippi",
    "mssd": "U.S. District Court for the Southern District of Mississippi",
    "mtd": "U.S. District Court for the District of Montana",
    "nced": "U.S. District Court for the Eastern District of North Carolina",
    "ncmd": "U.S. District Court for the Middle District of North Carolina",
    "ncwd": "U.S. District Court for the Western District of North Carolina",
    "ndd": "U.S. District Court for the District of North Dakota",
    "ned": "U.S. District Court for the District of Nebraska",
    "nhd": "U.S. District Court for the District of New Hampshire",
    "njd": "U.S. District Court for the District of New Jersey",
    "nmd": "U.S. District Court for the District of New Mexico",
    "nvd": "U.S. District Court for the District of Nevada",
    "nyed": "U.S. District Court for the Eastern District of New York",
    "nynd": "U.S. District Court for the Northern District of New York",
    "nysd": "U.S. District Court for the Southern District of New York",
    "nywd": "U.S. District Court for the Western District of New York",
    "ohnd": "U.S. District Court for the Northern District of Ohio",
    "ohsd": "U.S. District Court for the Southern District of Ohio",
    "oked": "U.S. District Court for the Eastern District of Oklahoma",
    "oknd": "U.S. District Court for the Northern District of Oklahoma",
    "okwd": "U.S. District Court for the Western District of Oklahoma",
    "ord": "U.S. District Court for the District of Oregon",
    "paed": "U.S. District Court for the Eastern District of Pennsylvania",
    "pamd": "U.S. District Court for the Middle District of Pennsylvania",
    "pawd": "U.S. District Court for the Western District of Pennsylvania",
    "prd": "U.S. District Court for the District of Puerto Rico",
    "rid": "U.S. District Court for the District of Rhode Island",
    "scd": "U.S. District Court for the District of South Carolina",
    "sdd": "U.S. District Court for the District of South Dakota",
    "tned": "U.S. District Court for the Eastern District of Tennessee",
    "tnmd": "U.S. District Court for the Middle District of Tennessee",
    "tnwd": "U.S. District Court for the Western District of Tennessee",
    "txed": "U.S. District Court for the Eastern District of Texas",
    "txnd": "U.S. District Court for the Northern District of Texas",
    "txsd": "U.S. District Court for the Southern District of Texas",
    "txwd": "U.S. District Court for the Western District of Texas",
    "utd": "U.S. District Court for the District of Utah",
    "vaed": "U.S. District Court for the Eastern District of Virginia",
    "vawd": "U.S. District Court for the Western District of Virginia",
    "vtd": "U.S. District Court for the District of Vermont",
    "waed": "U.S. District Court for the Eastern District of Washington",
    "wawd": "U.S. District Court for the Western District of Washington",
    "wied": "U.S. District Court for the Eastern District of Wisconsin",
    "wiwd": "U.S. District Court for the Western District of Wisconsin",
    "wvnd": "U.S. District Court for the Northern District of West Virginia",
    "wvsd": "U.S. District Court for the Southern District of West Virginia",
    "wyd": "U.S. District Court for the District of Wyoming",
    # Bankruptcy courts
    "almb": "U.S. Bankruptcy Court for the Middle District of Alabama",
    "cacb": "U.S. Bankruptcy Court for the Central District of California",
    "canb": "U.S. Bankruptcy Court for the Northern District of California",
    "ilnb": "U.S. Bankruptcy Court for the Northern District of Illinois",
    "nysb": "U.S. Bankruptcy Court for the Southern District of New York",
    "nyeb": "U.S. Bankruptcy Court for the Eastern District of New York",
    "txsb": "U.S. Bankruptcy Court for the Southern District of Texas",
    "deb":  "U.S. Bankruptcy Court for the District of Delaware",
    # Circuit Courts of Appeals
    "ca1": "U.S. Court of Appeals for the First Circuit",
    "ca2": "U.S. Court of Appeals for the Second Circuit",
    "ca3": "U.S. Court of Appeals for the Third Circuit",
    "ca4": "U.S. Court of Appeals for the Fourth Circuit",
    "ca5": "U.S. Court of Appeals for the Fifth Circuit",
    "ca6": "U.S. Court of Appeals for the Sixth Circuit",
    "ca7": "U.S. Court of Appeals for the Seventh Circuit",
    "ca8": "U.S. Court of Appeals for the Eighth Circuit",
    "ca9": "U.S. Court of Appeals for the Ninth Circuit",
    "ca10": "U.S. Court of Appeals for the Tenth Circuit",
    "ca11": "U.S. Court of Appeals for the Eleventh Circuit",
    "cadc": "U.S. Court of Appeals for the D.C. Circuit",
    "cafc": "U.S. Court of Appeals for the Federal Circuit",
    # Specialty courts
    "uscfc": "U.S. Court of Federal Claims",
    "cofc": "U.S. Court of Federal Claims",
    "cit": "U.S. Court of International Trade",
}

# ── Patterns that indicate a BAD court value ─────────────────────────
# These are document descriptions, not court names.
BAD_COURT_PATTERNS = [
    r"^complaint$",
    r"^motion",
    r"^order",
    r"^court\s+(grants|denies|rules|affirms|reverses|enters|issues|dismisses|certif|vacat)",
    r"^(amended|first|second|third|fourth|initial|original)\s+(complaint|motion|order|petition)",
    r"^(opinion|ruling|decision|judgment|verdict|settlement|memorandum|brief|response|reply|notice|stipulat|declaration|affidavit|exhibit|transcript|summons|subpoena|warrant|writ|injunction|mandamus|habeas|certiorari)",
    r"^MDL\b",
    r"^(TRO|preliminary|permanent)\b",
    r"^(class\s+action|class\s+cert)",
    r"^(plaintiff|defendant|petitioner|respondent|appellant|appellee)",
    r"^(summary\s+judgment|default\s+judgment|consent\s+decree)",
    r"^(discovery|deposition|interrogat|admission|production)",
    r"^(appeal|petition\s+for|request\s+for|denial\s+of|grant\s+of)",
    r"^(scheduling|status|case\s+management|pretrial|pre-trial)",
    r"date\s+(terminated|filed|entered|closed|opened|received|served)",
    r"^\d+.*LEXIS",
    r"^\d+.*WL\s",
    r"^\d+\s+(F\.|S\.Ct\.|L\.Ed|U\.S\.)",
    r"see\s+schedule",
    r"^(clearview|facebook|google|amazon|apple|microsoft|uber|lyft|tesla|meta)\b",
    r"^(ACLU|EFF|FTC|DOJ|SEC|EEOC|ICE|CBP|NYPD|LAPD)\b",
    r"denying.*motion",
    r"granting.*motion",
    r"'s\s+(motion|brief|response|reply|complaint|petition|appeal)",
]

BAD_COURT_RE = re.compile("|".join(BAD_COURT_PATTERNS), re.IGNORECASE)

# ── Valid court indicators ───────────────────────────────────────────
VALID_COURT_WORDS = re.compile(
    r"(district\s+court|circuit\s+court|court\s+of\s+appeals|supreme\s+court"
    r"|superior\s+court|county\s+court|bankruptcy\s+court|federal\s+court"
    r"|court\s+of\s+claims|court\s+of\s+common\s+pleas|u\.s\.\s+district"
    r"|chancery\s+court|probate\s+court|municipal\s+court|family\s+court"
    r"|tax\s+court|magistrate\s+court|appellate\s+court|court\s+of\s+appeal"
    r"|tribunal|high\s+court|crown\s+court)",
    re.IGNORECASE,
)


def is_bad_court(val: str) -> bool:
    """
    Check if a court value is NOT a real court name.
    
    Strategy: A court value is GOOD only if it contains a recognized court 
    keyword. Everything else is treated as garbage (document descriptions 
    that leaked into the court field).
    """
    if not val or not val.strip():
        return True
    val = val.strip()
    if len(val) < 4:
        return True
    # A value is valid ONLY if it contains a recognized court word
    if VALID_COURT_WORDS.search(val):
        return False
    # Some known abbreviations that are valid courts
    valid_abbrevs = [
        r"^[NSEW]\.?D\.?\s+(cal|tex|ill|fla|ga|ny|pa|ohio|mich|va|mass|conn|la|md|mo|wi|minn|wash|ind|ky|tenn|ala|miss|ark|iowa|kan|neb|okla|ore|utah|nev|nm|nd|sd|vt|nh|ri|me|wyo|mt|id|hi|ak|sc|nc|wv|del|ariz|col)\b",
        r"^E\.?D\.?\s",
        r"^W\.?D\.?\s",
        r"^M\.?D\.?\s",
        r"^S\.?D\.?\s",
        r"^N\.?D\.?\s",
        r"^D\.\s",
        r"^[1-9]\d*(st|nd|rd|th)\s+cir",
    ]
    for pat in valid_abbrevs:
        if re.search(pat, val, re.IGNORECASE):
            return False
    return True  # Anything else is garbage


def extract_court_code_from_url(url: str) -> str | None:
    """Extract PACER court code from CourtListener URL (docket, RECAP, or opinion)."""
    if not url:
        return None
    # RECAP URLs: gov.uscourts.XXXX.12345
    m = re.search(r"gov\.uscourts\.(\w+)\.", url)
    if m:
        return m.group(1)
    # Docket URLs may not have gov.uscourts but could still be parsed from the path
    return None


def extract_case_name_from_sources(source_titles: list[str]) -> str | None:
    """
    Try to extract a proper case name from secondary source titles.

    Looks for "X v. Y" patterns, "In re X" patterns, and also
    news headline patterns like "X Sues Y", "Lawsuit Against X".
    """
    # Regex for "Party v. Party" or "Party vs. Party" or "Party v Party"
    vs_pattern = re.compile(
        r"([A-Z][A-Za-z\s.\'&,()\-]+?)\s+(?:v\.?s?\.?)\s+([A-Z][A-Za-z\s.\'&,()\-]+)",
    )
    # "In re Something" pattern
    in_re_pattern = re.compile(
        r"(In\s+re\s+[A-Z][A-Za-z\s.\'&,()\-]+)",
        re.IGNORECASE,
    )

    for title in source_titles:
        if not title:
            continue
        # Try v. pattern
        m = vs_pattern.search(title)
        if m:
            name = f"{m.group(1).strip()} v. {m.group(2).strip()}"
            name = re.sub(r"\s+", " ", name).strip()
            # Trim trailing punctuation
            name = re.sub(r"[,;:\-–—]+$", "", name).strip()
            if 10 < len(name) < 200:
                return name
        # Try In re pattern
        m = in_re_pattern.search(title)
        if m:
            name = m.group(1).strip()
            name = re.sub(r"[,;:\-–—]+$", "", name).strip()
            if 5 < len(name) < 200:
                return name

    return None


def build_case_name_from_url_slug(url: str) -> str | None:
    """
    Extract case name from CourtListener docket/opinion URL slug.
    e.g., /docket/12345/smith-v-jones/ → "Smith v. Jones"
          /opinion/12345/gonzalez-v-google-inc/ → "Gonzalez v. Google Inc"
          /docket/12345/in-re-clearview-ai-inc-consumer-privacy-litigation/
              → "In Re Clearview Ai Inc Consumer Privacy Litigation"
    """
    if not url:
        return None

    # Match docket or opinion URL patterns
    m = re.search(r"/(docket|opinion)/\d+(?:/\d+)?/([\w-]+)/?", url)
    if not m:
        return None

    slug = m.group(2)
    parts = slug.split("-")

    # Check for "in-re-..." pattern
    if len(parts) >= 3 and parts[0].lower() == "in" and parts[1].lower() == "re":
        name = "In re " + " ".join(p.capitalize() for p in parts[2:])
        return name

    # Check for "X-v-Y" pattern
    if "v" in parts:
        v_idx = parts.index("v")
        if v_idx > 0 and v_idx < len(parts) - 1:
            plaintiff = " ".join(p.capitalize() for p in parts[:v_idx])
            defendant = " ".join(p.capitalize() for p in parts[v_idx + 1:])
            name = f"{plaintiff} v. {defendant}"
            # Clean up common suffixes
            name = re.sub(r"\s+Inc$", " Inc.", name)
            name = re.sub(r"\s+Llc$", " LLC", name)
            name = re.sub(r"\s+Corp$", " Corp.", name)
            name = re.sub(r"\s+Ltd$", " Ltd.", name)
            return name

    return None


def extract_name_from_headline(titles: list[str]) -> str | None:
    """
    Extract case parties from news headlines.
    e.g., "OpenAI Sued Over Using YouTube Videos" → uses "OpenAI" as key entity
    """
    # Patterns for "X sues Y" or "X sued by Y" or "lawsuit against X"
    sue_patterns = [
        re.compile(r"([A-Z][\w\s.&']+?)\s+(?:Sues?|Sued)\s+([A-Z][\w\s.&']+?)(?:\s+(?:Over|For|In|After|Alleging|Claiming)|$)", re.IGNORECASE),
        re.compile(r"([A-Z][\w\s.&']+?)\s+(?:Files?\s+(?:Suit|Lawsuit|Class\s+Action))\s+(?:Against\s+)?([A-Z][\w\s.&']+?)(?:\s+(?:Over|For|In|After)|$)", re.IGNORECASE),
    ]
    
    for title in titles:
        if not title:
            continue
        for pat in sue_patterns:
            m = pat.search(title)
            if m:
                p1 = m.group(1).strip()
                p2 = m.group(2).strip()
                if len(p1) > 2 and len(p2) > 2 and len(p1) < 60 and len(p2) < 60:
                    return f"{p1} v. {p2}"

    return None


def fix_all_cases():
    """Main fix function."""
    session = SessionLocal()

    try:
        all_cases = session.query(Case).all()
        logger.info("Processing %d cases", len(all_cases))

        # Preload document URLs for each case (for court extraction)
        doc_urls = {}
        for doc in session.query(Document).all():
            doc_urls.setdefault(doc.case_id, []).append(doc.url)

        # Preload secondary source titles and URLs for each case
        ss_data = {}
        for ss in session.query(SecondarySource).all():
            ss_data.setdefault(ss.case_id, []).append({
                "title": ss.source_title,
                "url": ss.url,
            })

        # Preload raw_document extra_fields for citations
        raw_cites = {}
        for rd in session.query(RawDocument).filter(
            RawDocument.extra_fields.isnot(None)
        ).all():
            ef = rd.extra_fields or {}
            cite = ef.get("cite_or_reference")
            if cite and str(cite).strip():
                raw_cites.setdefault(rd.case_id, []).append(str(cite).strip())

        stats = {
            "court_from_url": 0,
            "court_cleared": 0,
            "court_kept": 0,
            "name_from_sources": 0,
            "name_from_docket_url": 0,
            "name_from_headline": 0,
            "name_kept_generic": 0,
            "marked_as_stub": 0,
            "marked_as_real": 0,
        }

        for case in all_cases:
            case_pk = case.id
            urls = doc_urls.get(case_pk, [])
            sources = ss_data.get(case_pk, [])
            cites = raw_cites.get(case.case_id, [])

            # ─── Fix court ───────────────────────────────────
            current_court = case.court
            new_court = None

            # Try to extract from CourtListener URLs in documents
            for url in urls:
                code = extract_court_code_from_url(url)
                if code and code in COURT_CODE_MAP:
                    new_court = COURT_CODE_MAP[code]
                    break

            # Also try secondary source URLs
            if not new_court:
                for ss in sources:
                    code = extract_court_code_from_url(ss.get("url", ""))
                    if code and code in COURT_CODE_MAP:
                        new_court = COURT_CODE_MAP[code]
                        break

            if new_court:
                case.court = new_court
                stats["court_from_url"] += 1
            elif current_court and is_bad_court(current_court):
                case.court = None
                stats["court_cleared"] += 1
            elif current_court:
                stats["court_kept"] += 1

            # ─── Fix case name ───────────────────────────────
            current_name = case.case_name or ""
            is_generic = (
                current_name.startswith("[Stub]")
                or current_name.startswith("AI Litigation Case #")
                or not current_name
            )

            if is_generic:
                # Strategy 1: Extract from CourtListener docket/opinion URL slugs
                # (most reliable - contains actual case caption)
                for url in urls:
                    new_name = build_case_name_from_url_slug(url)
                    if new_name:
                        stats["name_from_docket_url"] += 1
                        break

                if not new_name:
                    # Also check secondary source URLs
                    for ss in sources:
                        new_name = build_case_name_from_url_slug(ss.get("url", ""))
                        if new_name:
                            stats["name_from_docket_url"] += 1
                            break

                if not new_name:
                    # Strategy 2: Extract "X v. Y" or "In re X" from source titles
                    source_titles = [s["title"] for s in sources]
                    new_name = extract_case_name_from_sources(source_titles)
                    if new_name:
                        stats["name_from_sources"] += 1

                if not new_name:
                    # Strategy 3: Extract from news headline patterns
                    source_titles = [s["title"] for s in sources]
                    new_name = extract_name_from_headline(source_titles)
                    if new_name:
                        stats["name_from_headline"] += 1

                if new_name:
                    case.case_name = new_name
                else:
                    stats["name_kept_generic"] += 1

            # ─── Build summary from sources if missing ───────
            if not case.summary and sources:
                titles = [s["title"] for s in sources if s.get("title")]
                if titles:
                    case.summary = "Related sources: " + "; ".join(titles[:3])
                    if len(titles) > 3:
                        case.summary += f" (and {len(titles) - 3} more)"

            # ─── Add citation info if available ──────────────
            if cites and not case.summary:
                case.summary = "Citations: " + "; ".join(set(cites[:5]))

            # ─── Determine stub status ───────────────────────
            has_real_name = not (
                (case.case_name or "").startswith("[Stub]")
                or (case.case_name or "").startswith("AI Litigation Case #")
                or not case.case_name
            )
            has_real_court = case.court is not None
            has_documents = len(urls) > 0
            has_sources = len(sources) > 0

            # A case is "real" if it has a proper name OR a real court,
            # OR at least has documents/sources associated with it
            if has_real_name or has_real_court or has_documents or has_sources:
                case.is_stub = False
                stats["marked_as_real"] += 1
            else:
                case.is_stub = True
                stats["marked_as_stub"] += 1

        session.commit()

        # Print stats
        logger.info("=" * 60)
        logger.info("FIX RESULTS:")
        logger.info("=" * 60)
        for k, v in stats.items():
            logger.info("  %-25s %d", k, v)

        # Count final quality
        total = session.query(Case).count()
        real = session.query(Case).filter_by(is_stub=False).count()
        stubs = session.query(Case).filter_by(is_stub=True).count()
        has_court = session.query(Case).filter(Case.court.isnot(None)).count()
        generic_names = session.query(Case).filter(
            (Case.case_name.like("[Stub]%")) | (Case.case_name.like("AI Litigation Case%"))
        ).count()

        logger.info("")
        logger.info("FINAL STATE:")
        logger.info("  Total cases:       %d", total)
        logger.info("  Real cases:        %d", real)
        logger.info("  Stubs:             %d", stubs)
        logger.info("  With valid court:  %d", has_court)
        logger.info("  Generic names:     %d", generic_names)

    except Exception as e:
        session.rollback()
        logger.error("Error: %s", e, exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    fix_all_cases()
