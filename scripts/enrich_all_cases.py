"""
Enrich all stub cases with real data extracted from Document_Table and
Secondary_Source_Coverage_Table.

Sources of enrichment:
1. Court names from CourtListener URLs (gov.uscourts.XXX patterns)
2. Case names from secondary source titles (v. patterns)
3. Filing dates from earliest document dates
4. Case summaries built from document descriptions
5. Mark enriched cases as real (is_stub=False)
"""

import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import SyncSessionLocal
from db.models import Case, Document, SecondarySource, RawDocument, RawSecondarySource, ChangeLog

# Federal court code → full name mapping
COURT_MAP = {
    "ca1": "U.S. Court of Appeals, 1st Circuit",
    "ca2": "U.S. Court of Appeals, 2nd Circuit",
    "ca3": "U.S. Court of Appeals, 3rd Circuit",
    "ca4": "U.S. Court of Appeals, 4th Circuit",
    "ca5": "U.S. Court of Appeals, 5th Circuit",
    "ca6": "U.S. Court of Appeals, 6th Circuit",
    "ca7": "U.S. Court of Appeals, 7th Circuit",
    "ca8": "U.S. Court of Appeals, 8th Circuit",
    "ca9": "U.S. Court of Appeals, 9th Circuit",
    "ca10": "U.S. Court of Appeals, 10th Circuit",
    "ca11": "U.S. Court of Appeals, 11th Circuit",
    "cadc": "U.S. Court of Appeals, D.C. Circuit",
    "cafc": "U.S. Court of Appeals, Federal Circuit",
    "scotus": "U.S. Supreme Court",
    # District courts
    "almd": "M.D. Ala.", "alnd": "N.D. Ala.", "alsd": "S.D. Ala.",
    "akd": "D. Alaska", "azd": "D. Ariz.",
    "ared": "E.D. Ark.", "arwd": "W.D. Ark.",
    "cacd": "C.D. Cal.", "caed": "E.D. Cal.", "cand": "N.D. Cal.", "casd": "S.D. Cal.",
    "cod": "D. Colo.", "ctd": "D. Conn.", "ded": "D. Del.", "dcd": "D.D.C.",
    "flmd": "M.D. Fla.", "flnd": "N.D. Fla.", "flsd": "S.D. Fla.",
    "gamd": "M.D. Ga.", "gand": "N.D. Ga.", "gasd": "S.D. Ga.",
    "hid": "D. Haw.", "idd": "D. Idaho",
    "ilcd": "C.D. Ill.", "ilnd": "N.D. Ill.", "ilsd": "S.D. Ill.",
    "innd": "N.D. Ind.", "insd": "S.D. Ind.",
    "iand": "N.D. Iowa", "iasd": "S.D. Iowa",
    "ksd": "D. Kan.",
    "kyed": "E.D. Ky.", "kywd": "W.D. Ky.",
    "laed": "E.D. La.", "lamd": "M.D. La.", "lawd": "W.D. La.",
    "med": "D. Me.", "mdd": "D. Md.",
    "mad": "D. Mass.", "mied": "E.D. Mich.", "miwd": "W.D. Mich.",
    "mnd": "D. Minn.",
    "msnd": "N.D. Miss.", "mssd": "S.D. Miss.",
    "moed": "E.D. Mo.", "mowd": "W.D. Mo.",
    "mtd": "D. Mont.", "ned": "D. Neb.", "nvd": "D. Nev.",
    "nhd": "D. N.H.", "njd": "D. N.J.",
    "nmd": "D. N.M.",
    "nyed": "E.D.N.Y.", "nynd": "N.D.N.Y.", "nysd": "S.D.N.Y.", "nywd": "W.D.N.Y.",
    "ncmd": "M.D.N.C.", "nced": "E.D.N.C.", "ncwd": "W.D.N.C.",
    "ndd": "D. N.D.",
    "ohnd": "N.D. Ohio", "ohsd": "S.D. Ohio",
    "oked": "E.D. Okla.", "oknd": "N.D. Okla.", "okwd": "W.D. Okla.",
    "ord": "D. Or.",
    "paed": "E.D. Pa.", "pamd": "M.D. Pa.", "pawd": "W.D. Pa.",
    "rid": "D. R.I.", "scd": "D. S.C.",
    "sdd": "D. S.D.",
    "tned": "E.D. Tenn.", "tnmd": "M.D. Tenn.", "tnwd": "W.D. Tenn.",
    "txed": "E.D. Tex.", "txnd": "N.D. Tex.", "txsd": "S.D. Tex.", "txwd": "W.D. Tex.",
    "utd": "D. Utah", "vtd": "D. Vt.",
    "vaed": "E.D. Va.", "vawd": "W.D. Va.",
    "waed": "E.D. Wash.", "wawd": "W.D. Wash.",
    "wvnd": "N.D. W.Va.", "wvsd": "S.D. W.Va.",
    "wied": "E.D. Wis.", "wiwd": "W.D. Wis.",
    "wyd": "D. Wyo.",
    "jpml": "Judicial Panel on Multidistrict Litigation",
    "gud": "D. Guam", "nmid": "D. N. Mariana Is.", "prd": "D. P.R.", "vid": "D. V.I.",
}


def extract_court_from_urls(session, case_id_str):
    """Extract federal court name from CourtListener URLs."""
    docs = session.query(RawDocument).filter(
        RawDocument.case_id == case_id_str
    ).all()
    for doc in docs:
        url = doc.url or ""
        m = re.search(r"gov\.uscourts\.(\w+)\.", url)
        if m:
            code = m.group(1).lower()
            return COURT_MAP.get(code, f"U.S. Federal Court ({code})")
    return None


def extract_case_name_from_sources(session, case_id_str):
    """Extract case name from secondary source titles using v. pattern."""
    sources = session.query(RawSecondarySource).filter(
        RawSecondarySource.case_id == case_id_str
    ).all()
    
    # Try "Plaintiff v. Defendant" pattern from titles
    v_pattern = re.compile(
        r"(?:^|,\s*|[\s])("
        r"(?:In re|In the Matter of|"
        r"[A-Z][a-zA-Z'\-\.]+(?:\s+(?:of|de|van|del|the|du|et al)\s*\.?\s*)*[A-Z]?[a-zA-Z'\-\.]*)"
        r"\s+v\.\s+"
        r"(?:[A-Z][a-zA-Z'\-\.]+(?:\s+(?:of|de|van|del|the|du|et al|Inc|LLC|Corp|Ltd|Co)\s*\.?\s*)*[A-Z]?[a-zA-Z'\-\.]*)"
        r")"
    )
    
    for src in sources:
        title = src.source_title or ""
        m = v_pattern.search(title)
        if m:
            name = m.group(1).strip()
            # Clean up trailing punctuation
            name = re.sub(r"[,;:\.\s]+$", "", name)
            if len(name) > 5:
                return name
    
    # Broader patterns for "In re" or "In the Matter of" 
    in_re_pattern = re.compile(r"(In (?:re|the Matter of)\s+[A-Z][a-zA-Z'\-\.\s,]+?)(?:\s*[\(\[\-–—]|\s*$|,\s*\d)")
    for src in sources:
        title = src.source_title or ""
        m = in_re_pattern.search(title)
        if m:
            name = m.group(1).strip()
            name = re.sub(r"[,;:\.\s]+$", "", name)
            if len(name) > 5:
                return name
    
    return None


def extract_case_name_from_documents(session, case_id_str):
    """Try to extract case name from document titles/court field patterns."""
    docs = session.query(RawDocument).filter(
        RawDocument.case_id == case_id_str
    ).order_by(RawDocument.row_number).all()
    
    # The 'court' field often has document descriptions; look for recognizable patterns
    # Also check cite_or_reference for case citations
    for doc in docs:
        ef = doc.extra_fields or {}
        cite = ef.get("cite_or_reference", "") or ""
        # Citations often look like: "Smith v. Jones, 123 F.3d 456 (2020)"
        m = re.search(
            r"([A-Z][a-zA-Z'\-\.]+(?:\s+(?:of|de|van|del|the|du|et al)\s*\.?\s*)*)\s+v\.\s+([A-Z][a-zA-Z'\-\.]+(?:\s+(?:of|de|van|del|the|du|et al|Inc|LLC|Corp|Ltd|Co)\s*\.?\s*)*)",
            cite
        )
        if m:
            return m.group(0).strip().rstrip(",;:. ")
    
    return None


def extract_earliest_date(session, case_id_str):
    """Get earliest document date as filing date proxy."""
    from pipeline.transform import parse_date
    docs = session.query(RawDocument).filter(
        RawDocument.case_id == case_id_str
    ).all()
    dates = []
    for doc in docs:
        d = parse_date(doc.document_date)
        if d:
            dates.append(d)
    return min(dates) if dates else None


def build_summary_from_docs(session, case_id_str):
    """Build a brief summary from document descriptions."""
    docs = session.query(RawDocument).filter(
        RawDocument.case_id == case_id_str
    ).order_by(RawDocument.row_number).all()
    
    descriptions = []
    for doc in docs:
        title = doc.document_title or ""
        if title and title not in descriptions:
            descriptions.append(title)
    
    if not descriptions:
        return None
    
    # Create a concise summary of key filings
    summary_parts = descriptions[:5]  # First 5 document descriptions
    if len(descriptions) > 5:
        summary_parts.append(f"... and {len(descriptions) - 5} more filings")
    
    return "Key filings: " + "; ".join(summary_parts)


def main():
    session = SyncSessionLocal()
    try:
        stubs = session.query(Case).filter(Case.is_stub == True).all()
        print(f"Found {len(stubs)} stub cases to enrich")
        
        enriched = 0
        promoted = 0
        
        for case in stubs:
            cid = case.case_id
            changes = {}
            
            # 1. Extract court from URLs
            if not case.court or case.court.startswith("[") or len(case.court) > 100:
                court = extract_court_from_urls(session, cid)
                if court:
                    case.court = court
                    changes["court"] = court
            
            # 2. Extract case name from secondary sources, then documents
            if not case.case_name or case.case_name.startswith("[Stub]"):
                name = extract_case_name_from_sources(session, cid)
                if not name:
                    name = extract_case_name_from_documents(session, cid)
                if name:
                    case.case_name = name
                    changes["case_name"] = name
            
            # 3. Extract filing date
            if not case.filing_date:
                fdate = extract_earliest_date(session, cid)
                if fdate:
                    case.filing_date = fdate
                    changes["filing_date"] = str(fdate)
            
            # 4. Build summary
            if not case.summary:
                summary = build_summary_from_docs(session, cid)
                if summary:
                    case.summary = summary
                    changes["summary"] = summary[:80] + "..."
            
            # 5. Check if the "court" field from Document_Table is actually a 
            #    document description (not a court name) and fix it
            if case.court and len(case.court) > 60:
                # This is likely a document description, not a court name
                real_court = extract_court_from_urls(session, cid)
                if real_court:
                    case.court = real_court
                    changes["court"] = real_court
                else:
                    case.court = None  # Clear bad data
            
            # 6. Promote to real case if we have enough data
            has_name = case.case_name and not case.case_name.startswith("[Stub]")
            has_docs = session.query(Document).filter(Document.case_id == case.id).count() > 0
            
            if has_name or has_docs or case.court or case.filing_date:
                case.is_stub = False
                promoted += 1
                changes["is_stub"] = "false"
            
            if changes:
                enriched += 1
                # Log the enrichment
                session.add(ChangeLog(
                    table_name="cases",
                    record_id=case.id,
                    field_name="_bulk_enrich",
                    old_value=None,
                    new_value=str(list(changes.keys())),
                    editor_id="pipeline",
                    reason="Case enriched from document URLs and secondary sources",
                    actor_type="pipeline",
                    operation="update",
                    citation_justification="Auto-enriched from Document_Table and Secondary_Source_Coverage_Table",
                ))
        
        session.commit()
        
        # Also fix cases that still have [Stub] name but have documents
        remaining_stubs = session.query(Case).filter(
            Case.case_name.like("[Stub]%")
        ).all()
        
        renamed = 0
        for case in remaining_stubs:
            # Get doc count
            doc_count = session.query(Document).filter(Document.case_id == case.id).count()
            src_count = session.query(SecondarySource).filter(SecondarySource.case_id == case.id).count()
            
            if doc_count > 0 or src_count > 0:
                # Use first document title as a basis for the name
                doc = session.query(Document).filter(Document.case_id == case.id).first()
                src = session.query(SecondarySource).filter(SecondarySource.case_id == case.id).first()
                
                if doc and doc.document_title:
                    # Try to extract a case name from the document title
                    title = doc.document_title
                    m = re.search(r"([A-Z][a-zA-Z'\-]+\s+v\.\s+[A-Z][a-zA-Z'\-]+)", title)
                    if m:
                        case.case_name = m.group(1)
                        renamed += 1
                    else:
                        case.case_name = f"AI Litigation Case #{case.case_id}"
                        renamed += 1
                elif src and src.source_title:
                    case.case_name = f"AI Litigation Case #{case.case_id}"
                    renamed += 1
                
                case.is_stub = False
        
        session.commit()
        
        # Final counts
        total = session.query(Case).count()
        real = session.query(Case).filter(Case.is_stub == False).count()
        stubs_left = session.query(Case).filter(Case.is_stub == True).count()
        
        print(f"\n=== Enrichment Complete ===")
        print(f"Enriched: {enriched} cases")
        print(f"Promoted to real: {promoted} cases")
        print(f"Renamed stubs: {renamed} cases")
        print(f"Total cases: {total}")
        print(f"Real cases: {real}")
        print(f"Remaining stubs: {stubs_left}")
        
    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
