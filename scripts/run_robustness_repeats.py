#!/usr/bin/env python3
"""
scripts/run_robustness_repeats.py
Task 4: Robustness repeat runs on the 12 original array benchmarks.
Executes 2 independent repeat timing sessions (25 rounds each, paired, pinned core 0).
Saves raw and summary CSVs with distinct timestamps:
  results/timing_repeat1_raw_<ts>.csv
  results/timing_repeat2_raw_<ts>.csv
Reports between-session variation in results/between_session_variation.csv.
"""

import os
import sys
import time
import math
import random
import csv
import subprocess
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
VM_DEFAULT = REPO_ROOT / "vm" / "minil-vm-goto"
RESULTS_DIR = REPO_ROOT / "results"

MODES = ["U", "R", "F", "S", "H", "FS", "FH"]
ROUNDS = 25

ARRAY_12 = [
    "bsearch", "bubble", "fill_sum", "gather", "hist", "matmul",
    "matvec_p", "param_sum", "prefix", "rec_sum", "sieve", "stencil_p"
]
BENCHMARKS_WITH_CONTROL = ARRAY_12 + ["fib"]

def get_pinned_cmd(cmd):
    try:
        subprocess.check_call(["which", "taskset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ["taskset", "-c", "0"] + cmd
    except Exception:
        return cmd

def run_single_session(session_id):
    ts = int(time.time())
    print(f"\n=======================================================")
    print(f" Starting Robustness Repeat Session {session_id} (ts={ts})")
    print(f"=======================================================")
    
    # Pre-compile binaries into scratch
    scratch_dir = RESULTS_DIR / f"repeat_{session_id}_bins"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    mbc_files = {}
    for b in BENCHMARKS_WITH_CONTROL:
        mbc_files[b] = {}
        src = REPO_ROOT / "benchmarks" / f"{b}.minil"
        for m in MODES:
            mbc_path = scratch_dir / f"{b}_{m}.mbc"
            subprocess.check_call([
                "python3", "-m", "compiler.main",
                "--mode", m, "-o", str(mbc_path), str(src)
            ], cwd=str(REPO_ROOT))
            mbc_files[b][m] = mbc_path

    rng = random.Random(1000 + session_id * 100)
    raw_records = []
    per_round_times = {b: {m: [] for m in MODES} for b in BENCHMARKS_WITH_CONTROL}

    total_rounds = ROUNDS + 1 # 1 warmup + 25 measurement rounds

    for round_idx in range(total_rounds):
        is_warmup = (round_idx == 0)
        if round_idx % 5 == 0 or is_warmup:
            print(f"  [Session {session_id}] Round {round_idx}/{ROUNDS} {'(warm-up)' if is_warmup else ''}...")

        b_names = list(BENCHMARKS_WITH_CONTROL)
        rng.shuffle(b_names)

        for b in b_names:
            modes_order = list(MODES)
            rng.shuffle(modes_order)

            for m in modes_order:
                mbc_file = mbc_files[b][m]
                cmd = get_pinned_cmd([str(VM_DEFAULT), str(mbc_file)])
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
                
                t_ns = 0
                for line in proc.stderr.splitlines():
                    if line.startswith("TIME_NS:"):
                        t_ns = int(line.split(":")[1].strip())
                        break

                if not is_warmup and t_ns > 0:
                    per_round_times[b][m].append(t_ns)
                    raw_records.append({
                        "round": round_idx,
                        "benchmark": b,
                        "mode": m,
                        "time_ns": t_ns,
                        "time_s": f"{t_ns / 1e9:.9f}"
                    })

    # Save raw CSV
    raw_csv = RESULTS_DIR / f"timing_repeat{session_id}_raw_{ts}.csv"
    with open(raw_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["round", "benchmark", "mode", "time_ns", "time_s"])
        writer.writeheader()
        writer.writerows(raw_records)
    print(f"Saved raw data to {raw_csv}")

    # Compute geomean overhead per mode over the 12 array benchmarks
    overheads = {}
    for m in ["R", "F", "S", "H", "FS", "FH"]:
        bench_medians = []
        for b in ARRAY_12:
            ratios = []
            for rnd in range(ROUNDS):
                t_u = per_round_times[b]["U"][rnd]
                t_m = per_round_times[b][m][rnd]
                ratios.append(t_m / t_u)
            ratios.sort()
            med = ratios[len(ratios) // 2]
            bench_medians.append(med)
        
        gm = math.exp(sum(math.log(x) for x in bench_medians) / len(bench_medians))
        ovh_pct = (gm - 1.0) * 100.0
        overheads[m] = ovh_pct
        print(f"  [Session {session_id}] Mode {m}: {ovh_pct:+.2f}%")

    return ts, raw_csv, overheads

def main():
    print("Starting Task 4: Robustness repeat runs on 12 original array benchmarks.")
    
    # 1. Baseline session from timing_summary.csv or paper_numbers.json
    baseline_overheads = {
        "R": 2.889959,
        "F": 3.650921,
        "S": 1.910298,
        "H": 0.579452,
        "FS": 2.408234,
        "FH": 1.806579
    }

    # 2. Run Session 1
    ts1, raw_csv1, ovh1 = run_single_session(1)
    
    # 3. Small pause, then run Session 2
    time.sleep(2)
    ts2, raw_csv2, ovh2 = run_single_session(2)

    # 4. Collate between-session variation
    modes = ["R", "F", "S", "H", "FS", "FH"]
    results = []

    print("\n--- Summary of Between-Session Variation ---")
    for m in modes:
        v0 = baseline_overheads[m]
        v1 = ovh1[m]
        v2 = ovh2[m]
        vals = [v0, v1, v2]
        mean_val = sum(vals) / 3.0
        variance = sum((x - mean_val) ** 2 for x in vals) / 2.0
        std_dev = math.sqrt(variance)
        val_range = max(vals) - min(vals)

        print(f"Mode {m:2s} | Baseline: {v0:+.2f}% | Repeat 1: {v1:+.2f}% | Repeat 2: {v2:+.2f}% | Mean: {mean_val:+.2f}% | StdDev: {std_dev:.2f}% | Range: {val_range:.2f}%")
        results.append({
            "mode": m,
            "baseline_ovh_pct": f"{v0:+.2f}%",
            "repeat1_ovh_pct": f"{v1:+.2f}%",
            "repeat2_ovh_pct": f"{v2:+.2f}%",
            "session_mean_pct": f"{mean_val:+.2f}%",
            "session_std_pct": f"{std_dev:.2f}%",
            "session_range_pct": f"{val_range:.2f}%",
            "repeat1_raw_file": raw_csv1.name,
            "repeat2_raw_file": raw_csv2.name
        })

    out_csv = RESULTS_DIR / "between_session_variation.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "mode", "baseline_ovh_pct", "repeat1_ovh_pct", "repeat2_ovh_pct",
            "session_mean_pct", "session_std_pct", "session_range_pct",
            "repeat1_raw_file", "repeat2_raw_file"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nBetween-session variation report saved to: {out_csv}")

if __name__ == "__main__":
    main()
