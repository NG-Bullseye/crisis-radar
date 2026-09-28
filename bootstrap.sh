#!/usr/bin/env bash
# Bootstrap: .venv + editable install with dev extras + data dir. Idempotent; starts no timer,
# no service, runs no research (crisis-radar run stays a manual/cron call).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# venv: created and filled only when missing; an existing .venv is left alone.
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]"
fi

# Runtime data (reports, cache) — git-ignored.
mkdir -p data

# Secrets are never written here; only report the missing file.
[ -f .env ] || echo "No .env — create it from the template if needed: cp .env.example .env"

echo "Done. Check: .venv/bin/crisis-radar --help && .venv/bin/python -m pytest -q"
