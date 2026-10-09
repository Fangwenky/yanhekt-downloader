#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'import playwright, yt_dlp' 2>/dev/null; then
  .venv/bin/pip install -r requirements.txt
fi
.venv/bin/playwright install chromium
exec .venv/bin/python app.py "$@"
