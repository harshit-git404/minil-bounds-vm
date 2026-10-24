#!/usr/bin/env bash
# Windows MSYS2 Bash Timing Harness for MiniL (Task 10)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=========================================================="
echo " Running MiniL Timing Benchmark Suite on Windows (MSYS2)"
echo "=========================================================="

if [ ! -f "vm/minil-vm.exe" ]; then
    echo "vm/minil-vm.exe not found! Running scripts/build_windows.sh..."
    bash scripts/build_windows.sh
fi

PYTHON=${PYTHON:-python3}

echo "Collecting environment details..."
$PYTHON scripts/collect_env.py results/env_windows.json "-O2 -std=c11"

echo "Executing benchmark timing harness..."
# On Windows MSYS2, run timing harness with windows VM path
VM_DEFAULT="vm/minil-vm.exe" VM_COUNT="vm/minil-vm-count.exe" $PYTHON scripts/run_timing_harness.py

echo "Windows benchmark execution complete! Results in results/"
