#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "No .venv found. Create one: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
exec .venv/bin/python -c "import server; server.app.run(host='127.0.0.1', port=5001, debug=False, threaded=True)"
