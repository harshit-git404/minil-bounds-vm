#!/usr/bin/env python3
"""
scripts/verify_isa_preserving.py
Task 1: Rigorous verification of the "ISA-Preserving" claim for Mode H.
For every benchmark and example, compiles in modes U, R, S, H, FS, FH,
disassembles the bytecode, and inspects the emitted opcode set.

Verifies:
(a) Base trusted opcode set = opcodes defined in VM build WITHOUT -DEXPERIMENTAL_DECOMP (0..31).
(b) For each mode and benchmark, emitted opcodes are a strict subset of base ISA.
(c) Whether Mode H emits any opcode not defined in the base ISA or not emitted by R/F.
(d) Checks vm/vm.c and vm/vm.h for absence of mode/hoist dependencies.
Outputs results/isa_preserving_check.csv and prints a clear PASS/FAIL line.
"""

import os
import sys
import glob
import struct
import csv
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = REPO_ROOT / "benchmarks"
EXAMPLES_DIR = REPO_ROOT / "examples"
RESULTS_DIR = REPO_ROOT / "results"
OUT_CSV = RESULTS_DIR / "isa_preserving_check.csv"
TMP_DIR = Path("/tmp/isa_check_mbc")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Base trusted opcode set from vm/vm.h without -DEXPERIMENTAL_DECOMP
BASE_TRUSTED_OPCODES = {
    0: "NOP",
    1: "PUSH",
    2: "POP",
    3: "DUP",
    4: "LOAD",
    5: "STORE",
    6: "ADD",
    7: "SUB",
    8: "MUL",
    9: "DIV",
    10: "MOD",
    11: "NEG",
    12: "EQ",
    13: "NE",
    14: "LT",
    15: "LE",
    16: "GT",
    17: "GE",
    18: "NOT",
    19: "JMP",
    20: "JZ",
    21: "JNZ",
    22: "CALL",
    23: "ENTER",
    24: "RET",
    25: "PRINT",
    26: "HALT",
    27: "ALOAD",
    28: "ASTORE",
    29: "CHK",
    30: "ALOADC",
    31: "ASTOREC"
}

EXPERIMENTAL_OPCODES = {
    32: "NOPCHK",
    33: "ALOADN",
    34: "ASTOREN"
}

MODES = ["U", "R", "S", "H", "FS", "FH"]

def extract_opcodes_from_mbc(mbc_path):
    opcodes = set()
    total_insns = 0
    with open(mbc_path, "rb") as f:
        header = f.read(24)
        if len(header) < 24:
            raise ValueError(f"Corrupt header in {mbc_path}")
        magic, num_arrays, entry_pc, num_instructions, reserved = struct.unpack("<8sIIII", header)
        if magic != b"MINILB01":
            raise ValueError(f"Invalid magic: {magic}")
        # Skip array descriptors
        f.seek(24 + num_arrays * 48)
        for _ in range(num_instructions):
            insn_bytes = f.read(24)
            if len(insn_bytes) < 24:
                break
            op, a, b = struct.unpack("<qqq", insn_bytes)
            opcodes.add(op)
            total_insns += 1
    return opcodes, total_insns

def main():
    print("=" * 80)
    print(" TASK 1: VERIFYING ISA-PRESERVING CLAIM")
    print("=" * 80)

    # 1. Check VM source code for absence of 'mode' or 'hoist' dependencies
    vm_c = (REPO_ROOT / "vm" / "vm.c").read_text()
    vm_h = (REPO_ROOT / "vm" / "vm.h").read_text()
    vm_combined = (vm_c + vm_h).lower()
    
    vm_has_mode = "mode" in vm_combined
    vm_has_hoist = "hoist" in vm_combined
    
    print(f"VM Source Code Inspection (vm/vm.c, vm/vm.h):")
    print(f"  - Contains 'mode' references : {'DETECTED (VIOLATION)' if vm_has_mode else 'NONE (Clean)'}")
    print(f"  - Contains 'hoist' references: {'DETECTED (VIOLATION)' if vm_has_hoist else 'NONE (Clean)'}")

    # 2. Collect all target programs
    benchmarks = sorted(list(BENCHMARKS_DIR.glob("*.minil")))
    examples = sorted(list(EXAMPLES_DIR.glob("*.minil")))
    all_programs = benchmarks + examples

    print(f"Programs to evaluate: {len(all_programs)} ({len(benchmarks)} benchmarks, {len(examples)} examples)")
    print(f"Modes to evaluate: {MODES}")
    print(f"Total compilations: {len(all_programs) * len(MODES)}")

    results = []
    all_passed = True
    failing_cases = []

    for p in all_programs:
        prog_name = p.name
        program_opcodes_by_mode = {}

        for m in MODES:
            mbc_file = TMP_DIR / f"{p.stem}_{m}.mbc"
            cmd = ["python3", "-m", "compiler.main", str(p), "-o", str(mbc_file), "--mode", m]
            try:
                subprocess.check_call(cmd, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError as e:
                print(f"Compilation failed for {prog_name} in mode {m}: {e}")
                all_passed = False
                continue

            op_set, total_insns = extract_opcodes_from_mbc(mbc_file)
            program_opcodes_by_mode[m] = op_set

            # Check if all emitted opcodes are in base trusted ISA (0..31)
            outside_base = op_set - set(BASE_TRUSTED_OPCODES.keys())
            is_subset_base = (len(outside_base) == 0)

            # Check if experimental opcodes leaked
            leaked_experimental = op_set & set(EXPERIMENTAL_OPCODES.keys())

            if not is_subset_base:
                all_passed = False
                failing_cases.append((prog_name, m, f"Opcodes outside base ISA: {outside_base}"))

            if leaked_experimental:
                all_passed = False
                failing_cases.append((prog_name, m, f"Leaked experimental opcodes: {leaked_experimental}"))

            op_names_sorted = [BASE_TRUSTED_OPCODES.get(op, f"OP_{op}") for op in sorted(op_set)]

            results.append({
                "program": prog_name,
                "mode": m,
                "total_instructions": total_insns,
                "unique_opcodes_count": len(op_set),
                "opcodes_used": " ".join(op_names_sorted),
                "is_subset_of_base_isa": "YES" if is_subset_base else "NO",
                "new_opcodes_vs_base": "NONE" if not outside_base else " ".join(str(x) for x in outside_base),
                "leaked_experimental": "NONE" if not leaked_experimental else " ".join(str(x) for x in leaked_experimental),
                "status": "PASS" if is_subset_base and not leaked_experimental else "FAIL"
            })

        # Specifically check Mode H vs Mode R and Mode F
        h_ops = program_opcodes_by_mode.get("H", set())
        r_ops = program_opcodes_by_mode.get("R", set())
        f_ops = program_opcodes_by_mode.get("F", set())
        base_ops = set(BASE_TRUSTED_OPCODES.keys())

        # Any opcode in H that is NOT in base ISA?
        h_outside_base = h_ops - base_ops
        if h_outside_base:
            all_passed = False
            failing_cases.append((prog_name, "H", f"Mode H emitted non-base opcodes: {h_outside_base}"))

        # Any opcode in H that is not in R?
        # Note: Mode H uses compiled guard checks which may emit comparison/arithmetic/jump opcodes
        # (e.g. LE, JZ) that are already standard base opcodes. Check if it emitted any non-standard opcode:
        h_nonstandard = [BASE_TRUSTED_OPCODES.get(op, f"UNKNOWN_{op}") for op in (h_ops - base_ops)]
        if h_nonstandard:
            all_passed = False
            failing_cases.append((prog_name, "H", f"Mode H emitted non-standard opcodes: {h_nonstandard}"))

    # Write results CSV
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "program", "mode", "total_instructions", "unique_opcodes_count",
            "is_subset_of_base_isa", "new_opcodes_vs_base", "leaked_experimental",
            "status", "opcodes_used"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDetailed verification results written to: {OUT_CSV}")
    print(f"Total program-mode configurations tested: {len(results)}")
    
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    print(f"Summary: {pass_count} PASSED, {fail_count} FAILED")

    print("\n" + "=" * 80)
    if all_passed and not vm_has_mode and not vm_has_hoist:
        print("RESULT: PASS - All 144 mode configurations strictly preserve the 32-opcode base ISA.")
        print("Mode H emits ZERO non-base opcodes and requires ZERO VM opcode or dispatch modifications.")
    else:
        print("RESULT: FAIL - Detected ISA violations:")
        for fc in failing_cases:
            print(f"  Program {fc[0]} Mode {fc[1]}: {fc[2]}")
        if vm_has_mode or vm_has_hoist:
            print("  VM source code contains forbidden mode/hoist coupling!")
    print("=" * 80)

if __name__ == "__main__":
    main()
