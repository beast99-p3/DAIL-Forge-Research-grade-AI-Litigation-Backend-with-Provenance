"""
pipeline/geo_map.py
-------------------
Maps US federal court abbreviation strings to (state_abbr, circuit) tuples.

Used by:
  - Migration 0007 to backfill cases.state / cases.circuit
  - pipeline/transform.py for new cases loaded from Excel
  - GET /cases?state=CA&circuit=9th filter

Usage::

    from pipeline.geo_map import classify_court
    state, circuit = classify_court("S.D.N.Y.")   # → ("NY", "2nd")
    state, circuit = classify_court("9th Cir.")    # → (None, "9th")
    state, circuit = classify_court("Unknown")     # → (None, None)
"""

from __future__ import annotations
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Exact-match lookup  {court_abbr_lower: (state, circuit)}
# ---------------------------------------------------------------------------

_EXACT: dict[str, tuple[Optional[str], Optional[str]]] = {
    # ── 1st Circuit ──────────────────────────────────────────────────────
    "1st cir.": (None, "1st"),
    "d. me.": ("ME", "1st"),
    "d. n.h.": ("NH", "1st"),
    "d. mass.": ("MA", "1st"),
    "d. r.i.": ("RI", "1st"),
    "d. p.r.": ("PR", "1st"),
    # ── 2nd Circuit ──────────────────────────────────────────────────────
    "2d cir.": (None, "2nd"),
    "2nd cir.": (None, "2nd"),
    "s.d.n.y.": ("NY", "2nd"),
    "e.d.n.y.": ("NY", "2nd"),
    "n.d.n.y.": ("NY", "2nd"),
    "w.d.n.y.": ("NY", "2nd"),
    "d. conn.": ("CT", "2nd"),
    "d. vt.": ("VT", "2nd"),
    # ── 3rd Circuit ──────────────────────────────────────────────────────
    "3d cir.": (None, "3rd"),
    "3rd cir.": (None, "3rd"),
    "e.d. pa.": ("PA", "3rd"),
    "m.d. pa.": ("PA", "3rd"),
    "w.d. pa.": ("PA", "3rd"),
    "d. n.j.": ("NJ", "3rd"),
    "d. del.": ("DE", "3rd"),
    "d.v.i.": ("VI", "3rd"),
    # ── 4th Circuit ──────────────────────────────────────────────────────
    "4th cir.": (None, "4th"),
    "d. md.": ("MD", "4th"),
    "e.d. va.": ("VA", "4th"),
    "w.d. va.": ("VA", "4th"),
    "n.d.w. va.": ("WV", "4th"),
    "s.d.w. va.": ("WV", "4th"),
    "d.s.c.": ("SC", "4th"),
    "e.d.n.c.": ("NC", "4th"),
    "m.d.n.c.": ("NC", "4th"),
    "w.d.n.c.": ("NC", "4th"),
    # ── 5th Circuit ──────────────────────────────────────────────────────
    "5th cir.": (None, "5th"),
    "n.d. tex.": ("TX", "5th"),
    "s.d. tex.": ("TX", "5th"),
    "e.d. tex.": ("TX", "5th"),
    "w.d. tex.": ("TX", "5th"),
    "e.d. la.": ("LA", "5th"),
    "w.d. la.": ("LA", "5th"),
    "m.d. la.": ("LA", "5th"),
    "n.d. miss.": ("MS", "5th"),
    "s.d. miss.": ("MS", "5th"),
    # ── 6th Circuit ──────────────────────────────────────────────────────
    "6th cir.": (None, "6th"),
    "n.d. ohio": ("OH", "6th"),
    "s.d. ohio": ("OH", "6th"),
    "e.d. mich.": ("MI", "6th"),
    "w.d. mich.": ("MI", "6th"),
    "e.d. ky.": ("KY", "6th"),
    "w.d. ky.": ("KY", "6th"),
    "e.d. tenn.": ("TN", "6th"),
    "m.d. tenn.": ("TN", "6th"),
    "w.d. tenn.": ("TN", "6th"),
    # ── 7th Circuit ──────────────────────────────────────────────────────
    "7th cir.": (None, "7th"),
    "n.d. ill.": ("IL", "7th"),
    "c.d. ill.": ("IL", "7th"),
    "s.d. ill.": ("IL", "7th"),
    "n.d. ind.": ("IN", "7th"),
    "s.d. ind.": ("IN", "7th"),
    "e.d. wis.": ("WI", "7th"),
    "w.d. wis.": ("WI", "7th"),
    # ── 8th Circuit ──────────────────────────────────────────────────────
    "8th cir.": (None, "8th"),
    "e.d. mo.": ("MO", "8th"),
    "w.d. mo.": ("MO", "8th"),
    "e.d. ark.": ("AR", "8th"),
    "w.d. ark.": ("AR", "8th"),
    "d. minn.": ("MN", "8th"),
    "d.n.d.": ("ND", "8th"),
    "d.s.d.": ("SD", "8th"),
    "d. neb.": ("NE", "8th"),
    "d. iowa": ("IA", "8th"),
    # ── 9th Circuit ──────────────────────────────────────────────────────
    "9th cir.": (None, "9th"),
    "n.d. cal.": ("CA", "9th"),
    "s.d. cal.": ("CA", "9th"),
    "c.d. cal.": ("CA", "9th"),
    "e.d. cal.": ("CA", "9th"),
    "d. ariz.": ("AZ", "9th"),
    "d. nev.": ("NV", "9th"),
    "d. or.": ("OR", "9th"),
    "w.d. wash.": ("WA", "9th"),
    "e.d. wash.": ("WA", "9th"),
    "d. mont.": ("MT", "9th"),
    "d. idaho": ("ID", "9th"),
    "d. alaska": ("AK", "9th"),
    "d. haw.": ("HI", "9th"),
    "d. guam": ("GU", "9th"),
    # ── 10th Circuit ─────────────────────────────────────────────────────
    "10th cir.": (None, "10th"),
    "d. colo.": ("CO", "10th"),
    "d. kan.": ("KS", "10th"),
    "d.n.m.": ("NM", "10th"),
    "n.d. okla.": ("OK", "10th"),
    "e.d. okla.": ("OK", "10th"),
    "w.d. okla.": ("OK", "10th"),
    "d. utah": ("UT", "10th"),
    "d. wyo.": ("WY", "10th"),
    # ── 11th Circuit ─────────────────────────────────────────────────────
    "11th cir.": (None, "11th"),
    "n.d. ala.": ("AL", "11th"),
    "m.d. ala.": ("AL", "11th"),
    "s.d. ala.": ("AL", "11th"),
    "n.d. fla.": ("FL", "11th"),
    "m.d. fla.": ("FL", "11th"),
    "s.d. fla.": ("FL", "11th"),
    "n.d. ga.": ("GA", "11th"),
    "m.d. ga.": ("GA", "11th"),
    "s.d. ga.": ("GA", "11th"),
    # ── D.C. Circuit ─────────────────────────────────────────────────────
    "d.c. cir.": ("DC", "D.C."),
    "d.d.c.": ("DC", "D.C."),
    # ── Supreme Court ────────────────────────────────────────────────────
    "s. ct.": (None, "SCOTUS"),
    "sup. ct.": (None, "SCOTUS"),
    "u.s. supreme court": (None, "SCOTUS"),
}

# ---------------------------------------------------------------------------
# State-keyword → state abbreviation for fuzzy fallback
# ---------------------------------------------------------------------------

_STATE_KEYWORDS: dict[str, str] = {
    "california": "CA", "texas": "TX", "new york": "NY", "florida": "FL",
    "illinois": "IL", "washington": "WA", "virginia": "VA", "ohio": "OH",
    "georgia": "GA", "michigan": "MI", "pennsylvania": "PA", "north carolina": "NC",
    "new jersey": "NJ", "arizona": "AZ", "colorado": "CO", "indiana": "IN",
    "tennessee": "TN", "maryland": "MD", "massachusetts": "MA", "minnesota": "MN",
    "missouri": "MO", "wisconsin": "WI", "alabama": "AL", "nevada": "NV",
    "oregon": "OR", "louisiana": "LA", "connecticut": "CT", "kentucky": "KY",
    "iowa": "IA", "mississippi": "MS", "arkansas": "AR", "kansas": "KS",
    "utah": "UT", "nebraska": "NE", "oklahoma": "OK", "new mexico": "NM",
    "hawaii": "HI", "alaska": "AK", "idaho": "ID", "montana": "MT",
    "wyoming": "WY", "south dakota": "SD", "north dakota": "ND",
    "south carolina": "SC", "west virginia": "WV", "delaware": "DE",
    "rhode island": "RI", "vermont": "VT", "new hampshire": "NH",
    "maine": "ME", "district of columbia": "DC", "d.c.": "DC",
    "puerto rico": "PR",
}

# ---------------------------------------------------------------------------
# Regex patterns for circuit references
# ---------------------------------------------------------------------------

_CIRCUIT_RE = re.compile(
    r"\b(1st|2d|2nd|3d|3rd|4th|5th|6th|7th|8th|9th|10th|11th|D\.C\.)\s+Cir",
    re.IGNORECASE,
)

_ORDINAL_NORMALIZE = {
    "2d": "2nd", "3d": "3rd",
}


def classify_court(court_text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Return ``(state_abbr, circuit)`` for a court string.

    Returns ``(None, None)`` when classification fails.

    Examples::

        classify_court("S.D.N.Y.")         → ("NY", "2nd")
        classify_court("9th Cir.")         → (None, "9th")
        classify_court("N.D. Cal.")        → ("CA", "9th")
        classify_court("Unknown court")    → (None, None)
    """
    if not court_text:
        return None, None

    lower = court_text.strip().lower()

    # 1. Exact match
    if lower in _EXACT:
        return _EXACT[lower]

    # 2. Substring match – find the longest matching key
    best_key, best_len = None, 0
    for key in _EXACT:
        if key in lower and len(key) > best_len:
            best_key, best_len = key, len(key)
    if best_key:
        return _EXACT[best_key]

    # 3. Circuit regex
    state: Optional[str] = None
    circuit: Optional[str] = None

    m = _CIRCUIT_RE.search(court_text)
    if m:
        raw = m.group(1)
        circuit = _ORDINAL_NORMALIZE.get(raw.lower(), raw.lower().replace("d.c.", "D.C."))
        if circuit not in ("D.C.",):
            circuit = circuit.capitalize() if circuit[0].isdigit() else circuit

    # 4. State keyword
    for keyword, abbr in _STATE_KEYWORDS.items():
        if keyword in lower:
            state = abbr
            break

    if state or circuit:
        return state, circuit

    return None, None
