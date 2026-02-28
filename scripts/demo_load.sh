#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# demo_load.sh – Load all Excel files into DAIL Forge database
# ─────────────────────────────────────────────────────────────────────
#
# Prerequisites:
#   1. Place Excel files in the ./data/ directory
#   2. Run: docker compose up -d
#
# Usage:
#   bash scripts/demo_load.sh
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-dail-forge-secret-key-change-me}"

echo "=================================================="
echo "  DAIL Forge – Loading Excel data via pipeline"
echo "=================================================="

# Option 1: Via API endpoint (recommended if API is running)
echo ""
echo "Triggering pipeline via POST /pipeline/load ..."
curl -s -X POST "${BASE_URL}/pipeline/load" \
  -H "X-API-Key: ${API_KEY}" | python3 -m json.tool

echo ""
echo "=================================================="
echo "  Pipeline complete. Check output above for any"
echo "  validation warnings."
echo "=================================================="

# Option 2: Via direct Python command (inside the container)
# docker compose exec api python -m pipeline.load_all
