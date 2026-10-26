#!/usr/bin/env bash
# scripts/demo.sh
# Task 6: Terminal demonstration and screenshot script for MiniL toolchain.
# Outputs clearly labeled sections (<=100 cols) and saves each to results/demo/NN_name.txt.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

exec python3 scripts/run_demo.py "$@"
