#!/bin/sh
set -e
exec python -m breachbench.agent_main "$@"
