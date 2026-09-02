#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "============================================================"
echo " Starting Vendor Onboarding Verification System"
echo "============================================================"

# Ensure virtualenv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

echo "Serving application on http://localhost:8000"
echo "Press Ctrl+C to stop."
echo "============================================================"

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
