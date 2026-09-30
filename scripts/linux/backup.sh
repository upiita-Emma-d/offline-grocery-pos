#!/usr/bin/env bash
# Daily verified backup (run by the tienda-pos-backup.timer). Keeps 30 copies locally and, if
# POS_BACKUP_DIR is set in .env and mounted (for example a USB drive), 30 more there.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
.venv/bin/python manage.py backup --dest data/backups --keep 30
EXTRA="$(sed -n 's/^POS_BACKUP_DIR=\(.*\)$/\1/p' .env 2>/dev/null | head -1)"
if [[ -n "$EXTRA" ]]; then
  if [[ -d "$(dirname "$EXTRA")" ]]; then
    .venv/bin/python manage.py backup --dest "$EXTRA" --keep 30
  else
    echo "$(date -Is) Backup drive $EXTRA not mounted; only the local copy was made."
  fi
fi
