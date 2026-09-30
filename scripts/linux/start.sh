#!/usr/bin/env bash
# Start the POS in the foreground with waitress (the systemd service does the same at boot).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PORT="$(sed -n 's/^POS_PORT=\([0-9]*\).*/\1/p' .env 2>/dev/null | head -1)"
.venv/bin/python manage.py migrate --noinput
exec .venv/bin/python -m waitress --listen="0.0.0.0:${PORT:-8008}" --threads=6 config.wsgi:application
