#!/usr/bin/env bash
# Simple admin checks (assumes server running at localhost:8000)
set -e
BASE=${1:-http://localhost:8000}

echo "Health:" 
curl -s $BASE/healthz | jq .

echo "\nAssignments summary:"
curl -s $BASE/admin/assignments | jq .

echo "\nResponses summary (recent):"
curl -s $BASE/admin/responses | jq .

# Note: requires jq installed on the machine to pretty-print JSON
