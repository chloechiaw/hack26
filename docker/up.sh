#!/usr/bin/env bash
# One-world dev stack (harness + hardened agent with --network none + unix IPC)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f db/worlds/world_0.db ]]; then
  echo "Provisioning db/worlds/world_0.db …"
  if [[ -f db/coffeeshop_seed.sql ]]; then
    sqlite3 db/coffeeshop.db < db/coffeeshop_seed.sql 2>/dev/null || true
  fi
  python db/scripts/generate_worlds.py
fi

docker compose -f docker/compose.yml build
docker compose -f docker/compose.yml up -d --remove-orphans

echo ""
echo "Harness  http://127.0.0.1:9000/health"
echo "Agent    docker logs -f bb-agent-0"
echo "Events   http://127.0.0.1:9000/events"
