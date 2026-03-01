#!/usr/bin/env python3
"""
Fix case data quality via direct SQL (avoids ORM caching issues).
"""

import os, sys, re, json, logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, text

DB_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://dail:dail_secret@db:5432/dail_forge",
)
engine = create_engine(DB_URL, echo=False)

# ── Federal court code → name mapping ────────────────────────────────
COURT_CODE_MAP = {
    "akd": "U.S. District Court, District of Alaska",
    "almd": "U.S. District Court, Middle District of Alabama",
    "alnd": "U.S. District Court, Northern District of Alabama",
    "alsd": "U.S. District Court, Southern District of Alabama",
    "ared": "U.S. District Court, Eastern District of Arkansas",
    "arwd": "U.S. District Court, Western District of Arkansas",
    "azd": "U.S. District Court, District of Arizona",
    "cacd": "U.S. District Court, Central District of California",
    "caed": "U.S. District Court, Eastern District of California",
    "cand": "U.S. District Court, Northern District of California",
    "casd": "U.S. District Court, Southern District of California",
    "cod": "U.S. District Court, District of Colorado",
    "ctd": "U.S. District Court, District of Connecticut",
    "dcd": "U.S. District Court, District of Columbia",
    "ded": "U.S. District Court, District of Delaware",
    "flmd": "U.S. District Court, Middle District of Florida",
    "flnd": "U.S. District Court, Northern District of Florida",
    "flsd": "U.S. District Court, Southern District of Florida",
    "gamd": "U.S. District Court, Middle District of Georgia",
    "gand": "U.S. District Court, Northern District of Georgia",
    "gasd": "U.S. District Court, Southern District of Georgia",
    "hid": "U.S. District Court, District of Hawaii",
    "iasd": "U.S. District Court, Southern District of Iowa",
    "iand": "U.S. District Court, Northern District of Iowa",
    "idd": "U.S. District Court, District of Idaho",
    "ilcd": "U.S. District Court, Central District of Illinois",
    "ilnd": "U.S. District Court, Northern District of Illinois",
    "ilsd": "U.S. District Court, Southern District of Illinois",
    "innd": "U.S. District Court, Northern District of Indiana",
    "insd": "U.S. District Court, Southern District of Indiana",
    "ksd": "U.S. District Court, District of Kansas",
    "kyed": "U.S. District Court, Eastern District of Kentucky",
    "kywd": "U.S. District Court, Western District of Kentucky",
    "laed": "U.S. District Court, Eastern District of Louisiana",
    "lamd": "U.S. District Court, Middle District of Louisiana",
    "lawd": "U.S. District Court, Western District of Louisiana",
    "mad": "U.S. District Court, District of Massachusetts",
    "mdd": "U.S. District Court, District of Maryland",
    "med": "U.S. District Court, District of Maine",
    "mied": "U.S. District Court, Eastern District of Michigan",
    "miwd": "U.S. District Court, Western District of Michigan",
    "mnd": "U.S. District Court, District of Minnesota",
    "moed": "U.S. District Court, Eastern District of Missouri",
    "mowd": "U.S. District Court, Western District of Missouri",
    "msnd": "U.S. District Court, Northern District of Mississippi",
    "mssd": "U.S. District Court, Southern District of Mississippi",
    "mtd": "U.S. District Court, District of Montana",
    "nced": "U.S. District Court, Eastern District of North Carolina",
    "ncmd": "U.S. District Court, Middle District of North Carolina",
    "ncwd": "U.S. District Court, Western District of North Carolina",
    "ndd": "U.S. District Court, District of North Dakota",
    "ned": "U.S. District Court, District of Nebraska",
    "nhd": "U.S. District Court, District of New Hampshire",
    "njd": "U.S. District Court, District of New Jersey",
    "nmd": "U.S. District Court, District of New Mexico",
    "nvd": "U.S. District Court, District of Nevada",
    "nyed": "U.S. District Court, Eastern District of New York",
    "nynd": "U.S. District Court, Northern District of New York",
    "nysd": "U.S. District Court, Southern District of New York",
    "nywd": "U.S. District Court, Western District of New York",
    "ohnd": "U.S. District Court, Northern District of Ohio",
    "ohsd": "U.S. District Court, Southern District of Ohio",
    "oked": "U.S. District Court, Eastern District of Oklahoma",
    "oknd": "U.S. District Court, Northern District of Oklahoma",
    "okwd": "U.S. District Court, Western District of Oklahoma",
    "ord": "U.S. District Court, District of Oregon",
    "paed": "U.S. District Court, Eastern District of Pennsylvania",
    "pamd": "U.S. District Court, Middle District of Pennsylvania",
    "pawd": "U.S. District Court, Western District of Pennsylvania",
    "prd": "U.S. District Court, District of Puerto Rico",
    "rid": "U.S. District Court, District of Rhode Island",
    "scd": "U.S. District Court, District of South Carolina",
    "sdd": "U.S. District Court, District of South Dakota",
    "tned": "U.S. District Court, Eastern District of Tennessee",
    "tnmd": "U.S. District Court, Middle District of Tennessee",
    "tnwd": "U.S. District Court, Western District of Tennessee",
    "txed": "U.S. District Court, Eastern District of Texas",
    "txnd": "U.S. District Court, Northern District of Texas",
    "txsd": "U.S. District Court, Southern District of Texas",
    "txwd": "U.S. District Court, Western District of Texas",
    "utd": "U.S. District Court, District of Utah",
    "vaed": "U.S. District Court, Eastern District of Virginia",
    "vawd": "U.S. District Court, Western District of Virginia",
    "vtd": "U.S. District Court, District of Vermont",
    "waed": "U.S. District Court, Eastern District of Washington",
    "wawd": "U.S. District Court, Western District of Washington",
    "wied": "U.S. District Court, Eastern District of Wisconsin",
    "wiwd": "U.S. District Court, Western District of Wisconsin",
    "wvnd": "U.S. District Court, Northern District of West Virginia",
    "wvsd": "U.S. District Court, Southern District of West Virginia",
    "wyd": "U.S. District Court, District of Wyoming",
    "almb": "U.S. Bankruptcy Court, Middle District of Alabama",
    "cacb": "U.S. Bankruptcy Court, Central District of California",
    "canb": "U.S. Bankruptcy Court, Northern District of California",
    "ilnb": "U.S. Bankruptcy Court, Northern District of Illinois",
    "nysb": "U.S. Bankruptcy Court, Southern District of New York",
    "nyeb": "U.S. Bankruptcy Court, Eastern District of New York",
    "txsb": "U.S. Bankruptcy Court, Southern District of Texas",
    "deb":  "U.S. Bankruptcy Court, District of Delaware",
    "ca1": "U.S. Court of Appeals, First Circuit",
    "ca2": "U.S. Court of Appeals, Second Circuit",
    "ca3": "U.S. Court of Appeals, Third Circuit",
    "ca4": "U.S. Court of Appeals, Fourth Circuit",
    "ca5": "U.S. Court of Appeals, Fifth Circuit",
    "ca6": "U.S. Court of Appeals, Sixth Circuit",
    "ca7": "U.S. Court of Appeals, Seventh Circuit",
    "ca8": "U.S. Court of Appeals, Eighth Circuit",
    "ca9": "U.S. Court of Appeals, Ninth Circuit",
    "ca10": "U.S. Court of Appeals, Tenth Circuit",
    "ca11": "U.S. Court of Appeals, Eleventh Circuit",
    "cadc": "U.S. Court of Appeals, D.C. Circuit",
    "cafc": "U.S. Court of Appeals, Federal Circuit",
    "uscfc": "U.S. Court of Federal Claims",
    "cofc": "U.S. Court of Federal Claims",
    "cit": "U.S. Court of International Trade",
}

VALID_COURT_RE = re.compile(
    r"(district\s+court|circuit\s+court|court\s+of\s+appeals|supreme\s+court"
    r"|superior\s+court|county\s+court|bankruptcy\s+court|federal\s+court"
    r"|court\s+of\s+claims|court\s+of\s+common\s+pleas|u\.s\.\s+district"
    r"|chancery\s+court|probate\s+court|municipal\s+court|family\s+court"
    r"|tax\s+court|magistrate\s+court|appellate\s+court|court\s+of\s+appeal"
    r"|tribunal|high\s+court|crown\s+court"
    r"|[NSEWMC]\.?D\.?\s+(Cal|Tex|Ill|Fla|Ga|N\.?Y|Pa|Ohio|Mich|Va|Mass|Conn|La|Md|Mo|Wi|Minn|Wash|Ind|Ky|Tenn|Ala|Miss|Ark|Iowa|Kan|Neb|Okla|Ore|Utah|Nev|N\.?M|N\.?D|S\.?D|Vt|N\.?H|R\.?I|Me|Wyo|Mont|Idaho|Haw|Alaska|S\.?C|N\.?C|W\.?Va|Del|Ariz|Col)"
    r"|[1-9]\d*(st|nd|rd|th)\s+cir"
    r")",
    re.IGNORECASE,
)


def extract_court_code(url):
    if not url:
        return None
    m = re.search(r"gov\.uscourts\.(\w+)\.", url)
    return m.group(1) if m else None


def extract_name_from_slug(url):
    if not url:
        return None
    m = re.search(r"/(docket|opinion)/\d+(?:/\d+)?/([\w-]+)/?", url)
    if not m:
        return None
    slug = m.group(2)
    parts = slug.split("-")
    if len(parts) >= 3 and parts[0].lower() == "in" and parts[1].lower() == "re":
        return "In re " + " ".join(p.capitalize() for p in parts[2:])
    if "v" in parts:
        v_idx = parts.index("v")
        if v_idx > 0 and v_idx < len(parts) - 1:
            p1 = " ".join(p.capitalize() for p in parts[:v_idx])
            p2 = " ".join(p.capitalize() for p in parts[v_idx + 1:])
            name = f"{p1} v. {p2}"
            for old, new in [(" Inc$", " Inc."), (" Llc$", " LLC"), (" Corp$", " Corp."), (" Ltd$", " Ltd.")]:
                name = re.sub(old, new, name)
            return name
    return None


def extract_vs_from_title(title):
    if not title:
        return None
    m = re.search(r"([A-Z][A-Za-z\s.\'&,()\-]+?)\s+(?:v\.?s?\.?)\s+([A-Z][A-Za-z\s.\'&,()\-]+)", title)
    if m:
        name = f"{m.group(1).strip()} v. {m.group(2).strip()}"
        name = re.sub(r"\s+", " ", name).strip()
        name = re.sub(r"[,;:\-\u2013\u2014]+$", "", name).strip()
        if 10 < len(name) < 200:
            return name
    m = re.search(r"(In\s+re\s+[A-Z][A-Za-z\s.\'&,()\-]+)", title, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        name = re.sub(r"[,;:\-\u2013\u2014]+$", "", name).strip()
        if 5 < len(name) < 200:
            return name
    return None


def extract_sue_from_title(title):
    if not title:
        return None
    m = re.search(
        r"([A-Z][\w\s.&\']+?)\s+(?:Sues?|Sued)\s+([A-Z][\w\s.&\']+?)(?:\s+(?:Over|For|In|After|Alleging|Claiming)|$)",
        title, re.IGNORECASE,
    )
    if m:
        p1, p2 = m.group(1).strip(), m.group(2).strip()
        if 2 < len(p1) < 60 and 2 < len(p2) < 60:
            return f"{p1} v. {p2}"
    m = re.search(
        r"([A-Z][\w\s.&\']+?)\s+(?:Files?\s+(?:Suit|Lawsuit|Class\s+Action))\s+(?:Against\s+)?([A-Z][\w\s.&\']+?)(?:\s+(?:Over|For|In|After)|$)",
        title, re.IGNORECASE,
    )
    if m:
        p1, p2 = m.group(1).strip(), m.group(2).strip()
        if 2 < len(p1) < 60 and 2 < len(p2) < 60:
            return f"{p1} v. {p2}"
    return None


def main():
    with engine.connect() as conn:
        # Test connection
        r = conn.execute(text("SELECT COUNT(*) FROM cases"))
        total = r.scalar()
        logger.info("Connected. Total cases: %d", total)

        # Load all cases
        cases = conn.execute(text(
            "SELECT id, case_id, case_name, court FROM cases ORDER BY id"
        )).fetchall()

        # Load document URLs per case (case_id is the PK in cases table)
        doc_rows = conn.execute(text(
            "SELECT case_id, url FROM documents WHERE url IS NOT NULL AND url != ''"
        )).fetchall()
        doc_urls = {}
        for r in doc_rows:
            doc_urls.setdefault(r[0], []).append(r[1])

        # Load secondary source data per case
        ss_rows = conn.execute(text(
            "SELECT case_id, source_title, url FROM secondary_sources"
        )).fetchall()
        ss_data = {}
        for r in ss_rows:
            ss_data.setdefault(r[0], []).append({"title": r[1], "url": r[2]})

        stats = {
            "court_from_url": 0, "court_cleared": 0, "court_kept": 0,
            "name_from_url_slug": 0, "name_from_source_vs": 0,
            "name_from_headline": 0, "name_from_source_title": 0,
            "name_kept_generic": 0,
        }

        updates = []
        for case_id, case_id_str, case_name, court in cases:
            urls = doc_urls.get(case_id, [])
            sources = ss_data.get(case_id, [])
            all_urls = urls + [s["url"] for s in sources if s.get("url")]

            new_court = None
            new_name = None

            # ── Fix court ──────────────────────────────────
            # Priority: Keep existing valid court > URL extraction > clear garbage
            if court and VALID_COURT_RE.search(court):
                new_court = court  # keep existing valid court
                stats["court_kept"] += 1
            else:
                # Try extracting from URLs only when current court is missing/bad
                extracted = None
                for url in all_urls:
                    code = extract_court_code(url)
                    if code and code in COURT_CODE_MAP:
                        extracted = COURT_CODE_MAP[code]
                        break

                if extracted:
                    new_court = extracted
                    stats["court_from_url"] += 1
                elif court:
                    new_court = None  # clear garbage
                    stats["court_cleared"] += 1
                else:
                    new_court = None

            # ── Fix name ───────────────────────────────────
            is_generic = (
                not case_name
                or case_name.startswith("[Stub]")
                or case_name.startswith("AI Litigation Case #")
            )

            if is_generic:
                # Strategy 1: CourtListener docket/opinion URL slugs
                for url in all_urls:
                    new_name = extract_name_from_slug(url)
                    if new_name:
                        stats["name_from_url_slug"] += 1
                        break

                # Strategy 2: "X v. Y" from source titles
                if not new_name:
                    for s in sources:
                        new_name = extract_vs_from_title(s.get("title"))
                        if new_name:
                            stats["name_from_source_vs"] += 1
                            break

                # Strategy 3: "X sues Y" headline patterns
                if not new_name:
                    for s in sources:
                        new_name = extract_sue_from_title(s.get("title"))
                        if new_name:
                            stats["name_from_headline"] += 1
                            break

                # Strategy 4: Use first informative source title as a descriptive name
                if not new_name and sources:
                    # Find the most informative source title
                    best_title = None
                    for s in sources:
                        t = (s.get("title") or "").strip()
                        if t and len(t) > 15 and not t.startswith("http"):
                            if len(t) > 120:
                                t = t[:117] + "..."
                            best_title = t
                            break
                    if best_title:
                        new_name = best_title
                        stats["name_from_source_title"] += 1

                # Strategy 5: Extract from URL path slugs (news sites, etc.)
                if not new_name:
                    for url in all_urls:
                        slug_name = extract_name_from_slug(url)
                        if slug_name:
                            new_name = slug_name
                            stats["name_from_url_slug"] += 1
                            break
                    if not new_name:
                        # Try non-CourtListener URL paths
                        for url in all_urls:
                            if not url:
                                continue
                            # Look for case name patterns in URL paths
                            m = re.search(r"/([a-z]+-v-[a-z][\w-]+)", url, re.IGNORECASE)
                            if m:
                                slug = m.group(1)
                                parts = slug.split("-")
                                if "v" in parts:
                                    v_i = parts.index("v")
                                    if v_i > 0 and v_i < len(parts) - 1:
                                        p1 = " ".join(p.capitalize() for p in parts[:v_i])
                                        p2 = " ".join(p.capitalize() for p in parts[v_i+1:])
                                        new_name = f"{p1} v. {p2}"
                                        stats["name_from_url_slug"] += 1
                                        break

                # Strategy 6: Clean up generic names with court info
                if not new_name:
                    case_num = re.search(r"#(\d+)", case_name or "")
                    num = case_num.group(1) if case_num else case_id_str
                    if new_court:
                        # Abbreviate court for compact display
                        short = new_court
                        short = short.replace("U.S. District Court, ", "")
                        short = short.replace("U.S. Court of Appeals, ", "")
                        short = short.replace("U.S. Bankruptcy Court, ", "Bankr. ")
                        new_name = f"AI Litigation ({short}) #{num}"
                    else:
                        new_name = f"AI Litigation Case #{num}"
                    stats["name_kept_generic"] += 1
            else:
                new_name = case_name

            # Record update if changed
            if new_court != court or new_name != case_name:
                updates.append((new_name, new_court, case_id))

        # Batch update
        logger.info("Applying %d updates...", len(updates))
        for name, court, cid in updates:
            conn.execute(
                text("UPDATE cases SET case_name = :name, court = :court WHERE id = :id"),
                {"name": name, "court": court, "id": cid},
            )
        conn.commit()
        logger.info("Committed.")

        # Verify
        r = conn.execute(text(
            "SELECT COUNT(*) FROM cases WHERE court IS NOT NULL"
        )).scalar()
        logger.info("Cases with court: %d", r)

        r = conn.execute(text(
            "SELECT COUNT(*) FROM cases WHERE case_name LIKE 'AI Lit%%' OR case_name LIKE '%%Stub%%'"
        )).scalar()
        logger.info("Generic names remaining: %d", r)

        # Print stats
        logger.info("=" * 50)
        for k, v in stats.items():
            logger.info("  %-25s %d", k, v)

        # Sample output
        logger.info("")
        logger.info("Sample cases:")
        rows = conn.execute(text(
            "SELECT id, case_name, court FROM cases ORDER BY id LIMIT 20"
        )).fetchall()
        for r in rows:
            logger.info("  ID=%d | %s | %s", r[0], r[1] or "(none)", r[2] or "(no court)")


if __name__ == "__main__":
    main()
