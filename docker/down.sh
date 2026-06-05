#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose -f docker/compose.yml down --remove-orphans 2>/dev/null || true
docker rm -f bb-harness-0 bb-agent-0 2>/dev/null || true
echo "Stopped breachbench compose stack"
