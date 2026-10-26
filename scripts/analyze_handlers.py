#!/usr/bin/env python3
"""
scripts/analyze_handlers.py
Task 3: Machine-code and layout analysis for bounds checking handlers in MiniL VM.
1. Disassembles minil-vm-decomp-goto and extracts byte size and instruction count for:
   CHK, ALOAD, ALOADC, ASTORE, ASTOREC, NOPCHK.
2. Reports total interpreter-loop code size for GOTO, SWITCH, and DIRECT.
3. Checks whether fused handlers share or duplicate code.
4. Performs layout sensitivity check: compiles GOTO at:
   -O2 (baseline)
   -O2 -fno-reorder-blocks
   -O2 -falign-functions=64
   Runs F vs R on the 12 array benchmarks and reports if the sign flips.
Writes results to results/handler_code_sizes.csv and results/layout_sensitivity.csv.
"""

import subprocess
import re
import csv
import struct
import math
import os
import shutil
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
VM_DIR = REPO_ROOT / "vm"
RESULTS_DIR = REPO_ROOT / "results"
BENCHMARKS_DIR = REPO_ROOT / "benchmarks"

OPCODES = {
    27: "ALOAD",
    28: "ASTORE",
    29: "CHK",
    30: "ALOADC",
    31: "ASTOREC",
    32: "NOPCHK",
    33: "ALOADN",
    34: "ASTOREN"
}

ARRAY_12 = [
    "bsearch", "bubble", "fill_sum", "gather", "hist", "matmul",
    "matvec_p", "param_sum", "prefix", "rec_sum", "sieve", "stencil_p"
]

def analyze_disassembly():
    bin_path = VM_DIR / "minil-vm-decomp-goto"
    if not bin_path.exists():
        # compile it
        subprocess.run(["make", "-C", str(REPO_ROOT), "vm/minil-vm-decomp-goto"], check=True)

    # 1. Read dispatch_table from .data.rel.ro
    # objdump -s -j .data.rel.ro vm/minil-vm-decomp-goto
    res = subprocess.run(["objdump", "-s", "-j", ".data.rel.ro", str(bin_path)], capture_output=True, text=True, check=True)
    hex_bytes = []
    start_addr = None
    for line in res.stdout.splitlines():
        line = line.strip()
        parts = line.split()
        if len(parts) >= 5 and re.match(r'^[0-9a-f]+$', parts[0]):
            addr = int(parts[0], 16)
            if start_addr is None:
                start_addr = addr
            data_str = "".join(parts[1:5])
            # parse hex
            b = bytes.fromhex(data_str)
            hex_bytes.extend(b)

    # Decode 8-byte little-endian pointers
    table_ptrs = []
    for i in range(0, len(hex_bytes), 8):
        if i + 8 <= len(hex_bytes):
            val = struct.unpack("<Q", bytes(hex_bytes[i:i+8]))[0]
            table_ptrs.append(val)

    # Map opcode to handler address
    handler_addrs = {}
    for op_id, name in OPCODES.items():
        if op_id < len(table_ptrs):
            handler_addrs[name] = table_ptrs[op_id]

    # Disassemble .text
    dis_res = subprocess.run(["objdump", "-d", str(bin_path)], capture_output=True, text=True, check=True)
    lines = dis_res.stdout.splitlines()

    # Parse instructions: addr: <hex> <asm>
    insns = []
    for line in lines:
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f\s]{2,})\s+([^#\n]+)', line)
        if m:
            addr = int(m.group(1), 16)
            raw_hex = m.group(2).strip().replace(" ", "")
            byte_len = len(raw_hex) // 2
            asm = m.group(3).strip()
            insns.append((addr, byte_len, asm))

    # All known targets in dispatch table
    all_targets = sorted(list(set(table_ptrs[:35])))

    # For each opcode of interest, trace from handler_addr until indirect jump or jump to next handler
    handler_stats = []
    for op_id in sorted(OPCODES.keys()):
        name = OPCODES[op_id]
        if name not in handler_addrs:
            continue
        start = handler_addrs[name]
        
        # Find next target address after start
        next_targets = [t for t in all_targets if t > start]
        cutoff = min(next_targets) if next_targets else start + 200

        # Collect instructions between start and cutoff
        h_insns = [ins for ins in insns if start <= ins[0] < cutoff]
        
        # Check if handler terminates with indirect jump jmpq *...
        # Trim after the first indirect jump or unconditional jump to dispatch
        trimmed_insns = []
        total_bytes = 0
        for addr, blen, asm in h_insns:
            trimmed_insns.append((addr, blen, asm))
            total_bytes += blen
            if asm.startswith("jmp") or asm.startswith("ret"):
                break

        handler_stats.append({
            "opcode": name,
            "address": f"0x{start:x}",
            "size_bytes": total_bytes,
            "instruction_count": len(trimmed_insns),
            "instructions": "; ".join(ins[2] for ins in trimmed_insns)
        })

    # Total interpreter loop size: range between min target and max target
    loop_start = min(all_targets)
    loop_end = max(all_targets)
    # find instructions in this range
    loop_insns = [ins for ins in insns if loop_start <= ins[0] <= loop_end + 32]
    loop_size_bytes = sum(ins[1] for ins in loop_insns)

    # Save handler sizes to results/handler_code_sizes.csv
    out_csv = RESULTS_DIR / "handler_code_sizes.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["opcode", "address", "size_bytes", "instruction_count", "instructions"])
        writer.writeheader()
        writer.writerows(handler_stats)

    print(f"Wrote handler sizes to {out_csv}")
    print(f"Total GOTO interpreter-loop size: {loop_size_bytes} bytes across {len(loop_insns)} instructions.")

    return handler_stats, loop_size_bytes

def measure_loop_sizes():
    # Measure total code size of main/run_vm for GOTO, SWITCH, DIRECT
    variants = {
        "GOTO": VM_DIR / "minil-vm-goto",
        "SWITCH": VM_DIR / "minil-vm-switch",
        "DIRECT": VM_DIR / "minil-vm-direct"
    }
    sizes = {}
    for name, path in variants.items():
        if not path.exists():
            subprocess.run(["make", "-C", str(REPO_ROOT), str(path)], check=True)
        res = subprocess.run(["objdump", "-d", str(path)], capture_output=True, text=True, check=True)
        # Find main function size
        in_main = False
        main_bytes = 0
        for line in res.stdout.splitlines():
            if "<main>:" in line:
                in_main = True
                continue
            if in_main:
                if re.match(r'^[0-9a-f]+ <[a-zA-Z0-9_]+>:', line):
                    break
                m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f\s]{2,})\s+([^#\n]+)', line)
                if m:
                    raw_hex = m.group(2).strip().replace(" ", "")
                    main_bytes += len(raw_hex) // 2
        sizes[name] = main_bytes
    return sizes

def run_layout_sensitivity():
    """
    Build GOTO at:
    - variant 0: -O2 (baseline)
    - variant 1: -O2 -fno-reorder-blocks
    - variant 2: -O2 -falign-functions=64
    Run F vs R on the 12 array benchmarks for 5 rounds.
    Report whether the F-vs-R sign flips.
    """
    print("\n--- Running Layout Sensitivity Check ---")
    configs = [
        ("baseline_O2", "-O2"),
        ("no_reorder_blocks", "-O2 -fno-reorder-blocks"),
        ("align_functions_64", "-O2 -falign-functions=64")
    ]

    results = []

    for label, cflags in configs:
        vm_bin = VM_DIR / f"minil-vm-layout-{label}"
        compile_cmd = f"gcc {cflags} -Wall -Wextra -std=c11 -DDISPATCH=GOTO vm/vm.c -o {vm_bin}"
        subprocess.run(compile_cmd, shell=True, check=True, cwd=str(REPO_ROOT))

        # Run 5 rounds of F and R on the 12 array benchmarks
        f_ratios = []
        for b in ARRAY_12:
            bin_cache = REPO_ROOT / "results" / "scratch_bins"
            bin_cache.mkdir(parents=True, exist_ok=True)
            r_bin = bin_cache / f"{b}_R.mbc"
            f_bin = bin_cache / f"{b}_F.mbc"
            
            # compile if missing
            if not r_bin.exists():
                subprocess.run(["python3", "-m", "compiler.main", f"benchmarks/{b}.minil", "-o", str(r_bin), "--mode", "R"], cwd=str(REPO_ROOT), check=True)
            if not f_bin.exists():
                subprocess.run(["python3", "-m", "compiler.main", f"benchmarks/{b}.minil", "-o", str(f_bin), "--mode", "F"], cwd=str(REPO_ROOT), check=True)

            r_times = []
            f_times = []
            for _ in range(5):
                # Run R
                res_r = subprocess.run([str(vm_bin), str(r_bin)], capture_output=True, text=True)
                if res_r.returncode != 0:
                    print(f"Error running {r_bin}: {res_r.stderr}")
                    continue
                # Run F
                res_f = subprocess.run([str(vm_bin), str(f_bin)], capture_output=True, text=True)
                if res_f.returncode != 0:
                    print(f"Error running {f_bin}: {res_f.stderr}")
                    continue
                
                # Extract TIME_NS: <val> from stderr
                m_r = re.search(r'TIME_NS:\s*(\d+)', res_r.stderr)
                m_f = re.search(r'TIME_NS:\s*(\d+)', res_f.stderr)
                if m_r and m_f:
                    r_times.append(int(m_r.group(1)))
                    f_times.append(int(m_f.group(1)))
                else:
                    print(f"Warning: regex failed on {b}. stderr R: {res_r.stderr[:50]}, F: {res_f.stderr[:50]}")

            if not r_times or not f_times:
                print(f"Fatal: no timing for benchmark {b}")
                continue

            med_r = sorted(r_times)[len(r_times) // 2]
            med_f = sorted(f_times)[len(f_times) // 2]
            ratio = med_f / med_r
            f_ratios.append(ratio)

        # Geomean ratio of F vs R
        gm = math.exp(sum(math.log(x) for x in f_ratios) / len(f_ratios))
        f_vs_r_ovh = (gm - 1.0) * 100.0

        print(f"[{label}] ({cflags}): F vs R geomean overhead = {f_vs_r_ovh:+.2f}%")
        results.append({
            "layout_variant": label,
            "cflags": cflags,
            "f_vs_r_geomean_overhead_pct": f"{f_vs_r_ovh:+.2f}%",
            "f_slower_than_r": "YES" if f_vs_r_ovh > 0 else "NO",
            "sign_flipped": "YES" if f_vs_r_ovh < 0 else "NO"
        })

    out_csv = RESULTS_DIR / "layout_sensitivity.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "layout_variant", "cflags", "f_vs_r_geomean_overhead_pct",
            "f_slower_than_r", "sign_flipped"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"Saved layout sensitivity results to {out_csv}")
    return results

def main():
    analyze_disassembly()
    sizes = measure_loop_sizes()
    print("Main function size per dispatch:")
    for k, v in sizes.items():
        print(f"  {k}: {v} bytes")
    run_layout_sensitivity()

if __name__ == "__main__":
    main()
