#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
N="${1:-50}"
export FLEET_PROJECT="${FLEET_PROJECT:-breachbench-fleet}"
PYTHONPATH=src python -m breachbench.orchestrator_main --down -n "$N" --project "$FLEET_PROJECT"
