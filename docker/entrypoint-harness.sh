#!/bin/sh
set -e
exec python -m breachbench.harness_main "$@"
