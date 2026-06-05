#!/usr/bin/env bash
# Build all three images (OrbStack: docker CLI works as-is)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker build -f docker/Dockerfile.harness -t breachbench/harness:latest .
docker build -f docker/Dockerfile.agent -t breachbench/agent:latest .
docker build -f docker/Dockerfile.orchestrator -t breachbench/orchestrator:latest .
echo "Built: breachbench/harness, breachbench/agent, breachbench/orchestrator"
