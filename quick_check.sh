#!/bin/bash

set -e

echo "Checking Python syntax..."
python3 -m py_compile app/main.py app/database.py

echo "Running app smoke checks..."
python3 tests/smoke_app.py

if [ "${SECURITY:-0}" = "1" ]; then
    echo "Running security smoke checks..."
    python3 tests/smoke_security.py
fi

echo "OK"
