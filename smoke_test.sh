#!/bin/bash

BASE="http://127.0.0.1:8000"

echo "Checking health..."
curl -s -o /dev/null -w "/health: %{http_code}\n" "$BASE/health"

echo "Checking public/login..."
curl -s -o /dev/null -w "/login: %{http_code}\n" "$BASE/login"

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
