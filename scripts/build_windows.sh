#!/usr/bin/env bash
# Build script for Windows using MSYS2 UCRT64 GCC (Task 10)
set -euo pipefail

echo "=========================================================="
echo " Building MiniL VM executables for Windows (MSYS2 UCRT64)"
echo "=========================================================="

CC=${CC:-gcc}
CFLAGS="-O2 -std=c11 -Wall -Wextra"

mkdir -p vm
mkdir -p results

echo "1. Building minil-vm-goto.exe (Computed goto dispatch)..."
$CC $CFLAGS -DDISPATCH=GOTO vm/vm.c -o vm/minil-vm-goto.exe

echo "2. Building minil-vm-switch.exe (Switch dispatch)..."
$CC $CFLAGS -DDISPATCH=SWITCH vm/vm.c -o vm/minil-vm-switch.exe

echo "3. Building minil-vm-direct.exe (Direct-threaded dispatch)..."
$CC $CFLAGS -DDISPATCH=DIRECT vm/vm.c -o vm/minil-vm-direct.exe

echo "4. Building minil-vm-count.exe (Dynamic check counting)..."
$CC $CFLAGS -DDISPATCH=GOTO -DCOUNT vm/vm.c -o vm/minil-vm-count.exe

echo "5. Building minil-vm-decomp-goto.exe (Experimental decomposition)..."
$CC $CFLAGS -DDISPATCH=GOTO -DEXPERIMENTAL_DECOMP vm/vm.c -o vm/minil-vm-decomp-goto.exe

echo "6. Building minil-vm-opt3.exe (-O3 optimization)..."
$CC -O3 -std=c11 -Wall -Wextra -DDISPATCH=GOTO vm/vm.c -o vm/minil-vm-opt3.exe

cp vm/minil-vm-goto.exe vm/minil-vm.exe

echo ""
echo "Windows build successful! Generated binaries:"
ls -lh vm/*.exe
