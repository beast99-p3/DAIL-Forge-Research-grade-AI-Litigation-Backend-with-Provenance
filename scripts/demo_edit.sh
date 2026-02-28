#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# demo_edit.sh – Curation API demo: edit a case + verify provenance
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-dail-forge-secret-key-change-me}"

echo "=================================================="
echo "  DAIL Forge – Curation API Demo"
echo "=================================================="

echo ""
echo "── 1. Create a citation first ──"
CITATION=$(curl -s -X POST "${BASE_URL}/citations" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "court_filing",
    "source_ref": "https://www.courtlistener.com/docket/123456/",
    "description": "Original court docket from PACER"
  }')
echo "$CITATION" | python3 -m json.tool
CITATION_ID=$(echo "$CITATION" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Created citation ID: ${CITATION_ID}"

echo ""
echo "── 2. Update case 1 (change status) with provenance ──"
curl -s -X PATCH "${BASE_URL}/cases/1" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"case_status\": \"Closed\",
    \"case_outcome\": \"Settled\",
    \"editor_id\": \"researcher@university.edu\",
    \"reason\": \"Updated based on latest PACER filing\",
    \"citation_id\": ${CITATION_ID}
  }" | python3 -m json.tool

echo ""
echo "── 3. Add a tag to case 1 ──"
curl -s -X POST "${BASE_URL}/cases/1/tags" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "tag_type": "issue",
    "value": "Facial Recognition",
    "editor_id": "researcher@university.edu",
    "reason": "Case involves facial recognition technology per complaint",
    "citation_justification": "Verified from complaint document para 12"
  }' | python3 -m json.tool

echo ""
echo "── 4. View the provenance ledger (change_log) for case 1 ──"
curl -s "${BASE_URL}/cases/1/change-log" | python3 -m json.tool

echo ""
echo "── 5. Edit without provenance (should fail with 422) ──"
echo "  Attempting PATCH without citation or justification..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "${BASE_URL}/cases/1" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "case_status": "Open",
    "editor_id": "rogue@hacker.com",
    "reason": "Just because"
  }')
echo "  HTTP status: ${HTTP_CODE} (expected 422)"

echo ""
echo "── 6. Edit without API key (should fail with 403/422) ──"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "${BASE_URL}/cases/1" \
  -H "Content-Type: application/json" \
  -d '{
    "case_status": "Open",
    "editor_id": "anon",
    "reason": "Unauthorized attempt",
    "citation_justification": "none"
  }')
echo "  HTTP status: ${HTTP_CODE} (expected 403 or 422)"

echo ""
echo "=================================================="
echo "  Provenance demo complete."
echo "  Every curated edit is tracked in change_log with:"
echo "    - editor_id, reason, old/new values"
echo "    - citation_id or citation_justification"
echo "=================================================="
