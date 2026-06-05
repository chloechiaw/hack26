#!/usr/bin/env bash
# Spin N worlds from the HOST (recommended for OrbStack). Avoids in-container path bugs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
N="${1:-50}"

if [[ ! -f db/worlds/world_0.db ]]; then
  sqlite3 db/coffeeshop.db < db/coffeeshop_seed.sql 2>/dev/null || true
  python db/scripts/generate_worlds.py
fi

docker build -f docker/Dockerfile.harness -t breachbench/harness:latest .
docker build -f docker/Dockerfile.agent -t breachbench/agent:latest .

export FLEET_PROJECT="${FLEET_PROJECT:-breachbench-fleet}"

PYTHONPATH=src python -m breachbench.orchestrator_main \
  -n "$N" \
  --ipc-root /tmp/breachbench \
  --project "$FLEET_PROJECT"

echo ""
echo "OrbStack group: $FLEET_PROJECT"
echo "Sample checks:"
echo "  curl http://127.0.0.1:9000/health"
echo "  docker ps --filter name=bb-harness | wc -l"
