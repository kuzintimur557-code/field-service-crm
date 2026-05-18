#!/bin/bash

set -e

BASE="${BASE:-http://127.0.0.1:8000}"

echo "Checking Python syntax..."
python3 -m py_compile app/main.py app/database.py

echo "Running local app smoke checks..."
python3 tests/smoke_app.py

echo "Running security smoke checks..."
python3 tests/smoke_security.py

echo "Checking HTTP server at $BASE..."
if curl -fsS --max-time 2 "$BASE/health" >/dev/null 2>&1; then
    curl -s -o /dev/null -w "/health: %{http_code}\n" "$BASE/health"
    curl -s -o /dev/null -w "/login: %{http_code}\n" "$BASE/login"
else
    echo "HTTP server not running; skipped /health and /login."
fi

echo "Done."
echo "Protected pages need browser login:"
echo "/"
echo "/clients"
echo "/catalog"
echo "/finance"
echo "/settings"
echo "/billing"
echo "/calls"
echo "/debug"
