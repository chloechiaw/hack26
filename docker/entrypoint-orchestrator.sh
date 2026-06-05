#!/bin/sh
set -e
exec python -m breachbench.orchestrator_main "$@"
