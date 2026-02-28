"""
Column-name mapping helpers.

The Excel exports use inconsistent header names. This module provides
fuzzy-matching so the loader can map any reasonable variant to our
canonical RAW-table column names.
"""

import re
from typing import Dict, Optional

# Canonical columns for each RAW table and their known aliases.
# Keys = canonical name, values = set of lowercased regex patterns.
CASE_ALIASES: Dict[str, list[str]] = {
    "case_id":        [r"case.?id", r"id"],
    "case_name":      [r"case.?name", r"caption", r"title", r"name"],
    "court":          [r"court", r"jurisdiction"],
    "filing_date":    [r"fil(e|ing).?date", r"date.?fil"],
    "closing_date":   [r"clos(e|ing).?date", r"date.?clos", r"end.?date"],
    "case_status":    [r"status"],
    "case_outcome":   [r"outcome", r"result", r"disposition"],
    "case_type":      [r"case.?type", r"type"],
    "plaintiff":      [r"plaintiff", r"claimant", r"petitioner"],
    "defendant":      [r"defendant", r"respondent"],
    "judge":          [r"judge", r"justice", r"magistrate"],
    "summary":        [r"summary", r"description", r"abstract", r"synopsis"],
    "issue_list":     [r"issue", r"issues"],
    "area_list":      [r"area", r"areas", r"sector"],
    "cause_list":     [r"cause", r"causes", r"claim"],
    "algorithm_list": [r"algorithm", r"algorithms", r"ai.?system", r"technology"],
    "harm_list":      [r"harm", r"harms", r"impact"],
}

DOCKET_ALIASES: Dict[str, list[str]] = {
    "case_id":       [r"case.?id", r"id"],
    "docket_number": [r"docket.?(number|no|num|#)", r"entry.?number", r"number"],
    "entry_date":    [r"date", r"entry.?date", r"filed.?date"],
    "entry_text":    [r"text", r"entry.?text", r"description", r"entry"],
    "filed_by":      [r"filed.?by", r"filer", r"party"],
}

DOCUMENT_ALIASES: Dict[str, list[str]] = {
    "case_id":         [r"case.?id", r"id"],
    "document_title":  [r"title", r"document.?title", r"name"],
    "document_type":   [r"type", r"document.?type", r"doc.?type"],
    "document_date":   [r"date", r"document.?date", r"filing.?date"],
    "url":             [r"url", r"link", r"href"],
}

SECONDARY_SOURCE_ALIASES: Dict[str, list[str]] = {
    "case_id":          [r"case.?id", r"id"],
    "source_title":     [r"title", r"source.?title", r"headline"],
    "source_type":      [r"type", r"source.?type"],
    "publication_date": [r"date", r"publication.?date", r"pub.?date", r"published"],
    "author":           [r"author", r"writer", r"by"],
    "url":              [r"url", r"link", r"href"],
}


def _normalise(header: str) -> str:
    """Lowercase, strip, collapse whitespace/underscores."""
    return re.sub(r"[\s_]+", " ", header.strip().lower())


def build_column_map(headers: list[str], aliases: Dict[str, list[str]]) -> Dict[str, str]:
    """
    Return {excel_header -> canonical_name} for every header we can match.
    Unmatched headers are NOT included (they go into extra_fields).
    """
    mapping: Dict[str, str] = {}
    used_canonical: set[str] = set()

    for header in headers:
        norm = _normalise(header)
        for canonical, patterns in aliases.items():
            if canonical in used_canonical:
                continue
            for pat in patterns:
                if re.search(pat, norm):
                    mapping[header] = canonical
                    used_canonical.add(canonical)
                    break
            if header in mapping:
                break

    return mapping
