#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# demo_query.sh – Example read & export API calls
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=================================================="
echo "  DAIL Forge – Research API Demo Queries"
echo "=================================================="

echo ""
echo "── 1. Health check ──"
curl -s "${BASE_URL}/health" | python3 -m json.tool

echo ""
echo "── 2. List cases (page 1, 5 per page) ──"
curl -s "${BASE_URL}/cases?page=1&page_size=5" | python3 -m json.tool

echo ""
echo "── 3. Filter by court ──"
curl -s "${BASE_URL}/cases?court=district&page_size=3" | python3 -m json.tool

echo ""
echo "── 4. Filter by tag type ──"
curl -s "${BASE_URL}/cases?tag_type=issue&page_size=3" | python3 -m json.tool

echo ""
echo "── 5. Filter by date range ──"
curl -s "${BASE_URL}/cases?date_from=2023-01-01&date_to=2025-12-31&page_size=3" | python3 -m json.tool

echo ""
echo "── 6. Get a single case (id=1) ──"
curl -s "${BASE_URL}/cases/1" | python3 -m json.tool

echo ""
echo "── 7. Get dockets for case 1 ──"
curl -s "${BASE_URL}/cases/1/dockets" | python3 -m json.tool

echo ""
echo "── 8. Get documents for case 1 ──"
curl -s "${BASE_URL}/cases/1/documents" | python3 -m json.tool

echo ""
echo "── 9. Get secondary sources for case 1 ──"
curl -s "${BASE_URL}/cases/1/secondary-sources" | python3 -m json.tool

echo ""
echo "── 10. CSV export (first 5 lines) ──"
curl -s "${BASE_URL}/export/cases.csv" | head -6

echo ""
echo "=================================================="
echo "  Done. See /docs for the full OpenAPI spec."
echo "=================================================="
