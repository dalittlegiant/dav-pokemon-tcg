#!/usr/bin/env bash
# Local helper: fetch prices, commit data files, push to main.
# Usage: ./push_update.sh [--with-analysis]
set -euo pipefail
cd "$(dirname "$0")"

# Load .env for local runs (GitHub Actions uses repository Secrets instead)
if [ -f .env ]; then
  set -a; source .env; set +a
fi

python update_prices.py "$@"

git add data/history_prices.json data/latest_summary.json
if git diff --cached --quiet; then
  echo "No data changes -- nothing to commit."
else
  git commit -m "tracker: price update $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push origin main
fi
