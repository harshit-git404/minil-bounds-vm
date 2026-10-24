#!/usr/bin/env python3
"""
Tasks 6 & 7: Dispatch-vs-comparison decomposition and dispatch ablation study.
Evaluates modes (U, N, R, F, FN, S, H, FS, FH) across dispatch techniques:
- GOTO (computed goto, -O2)
- SWITCH (switch dispatch, -O2)
- DIRECT (direct-threaded dispatch, -O2)
- OPT3 (computed goto, -O3)

Calculates:
- Paired ratios T_mode / T_U
- Fraction of separate check overhead (R) explained by dispatch (N) vs comparison
- Opcode fusion effect (F vs FN)
- Impact of dispatch architecture on check overheads
- Bootstrap 95% confidence intervals (2000 resamples)
"""
import glob
import json
import math
import os
import random
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.collect_env import collect_env

CONFIGS = {
    "GOTO": os.path.join(REPO_ROOT, "vm", "minil-vm-decomp-goto"),
    "SWITCH": os.path.join(REPO_ROOT, "vm", "minil-vm-decomp-switch"),
    "DIRECT": os.path.join(REPO_ROOT, "vm", "minil-vm-decomp-direct"),
    "OPT3": os.path.join(REPO_ROOT, "vm", "minil-vm-decomp-opt3"),
}

MODES = ["U", "N", "R", "F", "FN", "S", "H", "FS", "FH"]
ROUNDS = 15
BOOTSTRAP_RESAMPLES = 2000

def get_pinned_cmd(cmd):
    try:
        subprocess.check_call(["which", "taskset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ["taskset", "-c", "0"] + cmd
    except Exception:
        return cmd

def bootstrap_ci(values, num_resamples=BOOTSTRAP_RESAMPLES, alpha=0.05):
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    boot_medians = []
    rng = random.Random(1337)
    for _ in range(num_resamples):
        sample = [rng.choice(values) for _ in range(n)]
        sample.sort()
        boot_medians.append(sample[n // 2])
    boot_medians.sort()
    low_idx = int((alpha / 2.0) * num_resamples)
    high_idx = int((1.0 - alpha / 2.0) * num_resamples)
    return boot_medians[low_idx], boot_medians[high_idx]

def compile_benchmarks(benchmarks):
    print("Compiling all benchmarks for all modes...")
    bytecode_map = {}
    tmp_dir = "/tmp/minil_decomp_bins"
    os.makedirs(tmp_dir, exist_ok=True)

    for bench in benchmarks:
        bench_name = os.path.splitext(os.path.basename(bench))[0]
        bytecode_map[bench_name] = {}
        for mode in MODES:
            mbc_path = os.path.join(tmp_dir, f"{bench_name}_{mode}.mbc")
            cmd = ["python3", "-m", "compiler.main", "--mode", mode, "-o", mbc_path, bench]
            subprocess.check_call(cmd, cwd=REPO_ROOT)
            bytecode_map[bench_name][mode] = mbc_path
    return bytecode_map

def verify_checksums(benchmarks, bytecode_map):
    print("Verifying benchmark checksums across all modes and configurations...")
    default_vm = CONFIGS["GOTO"]
    for bench in benchmarks:
        bench_name = os.path.splitext(os.path.basename(bench))[0]
        baseline_out = None
        for mode in MODES:
            mbc = bytecode_map[bench_name][mode]
            proc = subprocess.run([default_vm, mbc], capture_output=True, text=True, cwd=REPO_ROOT)
            if proc.returncode != 0:
                raise RuntimeError(f"Benchmark {bench_name} failed in mode {mode}: {proc.stderr}")
            out_lines = [l for l in proc.stdout.splitlines() if not l.startswith("TIME_")]
            out_str = "\n".join(out_lines).strip()
            if baseline_out is None:
                baseline_out = out_str
            elif out_str != baseline_out:
                raise RuntimeError(f"Checksum mismatch for {bench_name} in mode {mode}: expected {baseline_out}, got {out_str}")
    print("All benchmark outputs verified successfully!")

def run_experiment():
    os.makedirs("results", exist_ok=True)
    collect_env("results/env.json", "-O2 / -O3")

    benchmarks = sorted(glob.glob(os.path.join(REPO_ROOT, "benchmarks", "*.minil")))
    bytecode_map = compile_benchmarks(benchmarks)
    verify_checksums(benchmarks, bytecode_map)

    raw_csv = "results/decomposition_raw.csv"
    with open(raw_csv, "w") as f:
        f.write("config,benchmark,round,mode,time_ns\n")

    timing_data = {} # (config, bench_name, mode) -> list of times

    for config_name, vm_bin in CONFIGS.items():
        print(f"\n================ Running configuration: {config_name} ================")
        for bench in benchmarks:
            bench_name = os.path.splitext(os.path.basename(bench))[0]
            print(f"Timing {bench_name} [{config_name}]...")

            # Warm-up round
            for m in MODES:
                mbc = bytecode_map[bench_name][m]
                subprocess.run(get_pinned_cmd([vm_bin, mbc]), capture_output=True, text=True, cwd=REPO_ROOT)

            # Measurement rounds
            for r in range(ROUNDS):
                shuffled_modes = list(MODES)
                random.shuffle(shuffled_modes)
                round_times = {}

                for m in shuffled_modes:
                    mbc = bytecode_map[bench_name][m]
                    proc = subprocess.run(get_pinned_cmd([vm_bin, mbc]), capture_output=True, text=True, cwd=REPO_ROOT)
                    t_ns = None
                    for l in proc.stderr.splitlines():
                        if l.startswith("TIME_NS:"):
                            t_ns = int(l.split(":")[1].strip())
                            break
                    if t_ns is None:
                        raise RuntimeError(f"Missing timing output for {bench_name} mode {m} round {r}")
                    round_times[m] = t_ns

                with open(raw_csv, "a") as f:
                    for m in MODES:
                        f.write(f"{config_name},{bench_name},{r},{m},{round_times[m]}\n")
                        key = (config_name, bench_name, m)
                        if key not in timing_data:
                            timing_data[key] = []
                        timing_data[key].append(round_times[m])

    # Summarize decomposition results (Task 6)
    decomp_summary_csv = "results/decomposition_summary.csv"
    with open(decomp_summary_csv, "w") as f:
        f.write("config,benchmark,r_overhead_pct,n_overhead_pct,f_overhead_pct,fn_overhead_pct,dispatch_share_pct,comp_share_pct,dispatch_share_ci_low,dispatch_share_ci_high\n")

    decomp_records = []

    for config_name in CONFIGS.keys():
        for bench in benchmarks:
            bench_name = os.path.splitext(os.path.basename(bench))[0]
            if bench_name == "fib":
                continue

            u_times = timing_data[(config_name, bench_name, "U")]
            n_times = timing_data[(config_name, bench_name, "N")]
            r_times = timing_data[(config_name, bench_name, "R")]
            f_times = timing_data[(config_name, bench_name, "F")]
            fn_times = timing_data[(config_name, bench_name, "FN")]

            r_ratios = [(r / u - 1.0) * 100.0 for r, u in zip(r_times, u_times)]
            n_ratios = [(n / u - 1.0) * 100.0 for n, u in zip(n_times, u_times)]
            f_ratios = [(f / u - 1.0) * 100.0 for f, u in zip(f_times, u_times)]
            fn_ratios = [(fn / u - 1.0) * 100.0 for fn, u in zip(fn_times, u_times)]

            r_ovh = sorted(r_ratios)[len(r_ratios)//2]
            n_ovh = sorted(n_ratios)[len(n_ratios)//2]
            f_ovh = sorted(f_ratios)[len(f_ratios)//2]
            fn_ovh = sorted(fn_ratios)[len(fn_ratios)//2]

            # Decomposition share per round: (t_N - t_U) / (t_R - t_U)
            round_shares = []
            for u, n, r in zip(u_times, n_times, r_times):
                denom = r - u
                if abs(denom) > 1e-9:
                    share = (n - u) / denom * 100.0
                    round_shares.append(share)

            if round_shares:
                sorted_shares = sorted(round_shares)
                med_share = sorted_shares[len(sorted_shares)//2]
                ci_low, ci_high = bootstrap_ci(round_shares)
            else:
                med_share, ci_low, ci_high = 0.0, 0.0, 0.0

            comp_share = 100.0 - med_share

            with open(decomp_summary_csv, "a") as f:
                f.write(f"{config_name},{bench_name},{r_ovh:.2f},{n_ovh:.2f},{f_ovh:.2f},{fn_ovh:.2f},{med_share:.2f},{comp_share:.2f},{ci_low:.2f},{ci_high:.2f}\n")

            decomp_records.append({
                "config": config_name,
                "benchmark": bench_name,
                "r_ovh": r_ovh,
                "n_ovh": n_ovh,
                "f_ovh": f_ovh,
                "fn_ovh": fn_ovh,
                "dispatch_share": med_share,
                "comp_share": comp_share,
                "dispatch_share_ci": [ci_low, ci_high]
            })

    # Summarize dispatch ablation (Task 7)
    ablation_summary_csv = "results/dispatch_ablation_summary.csv"
    with open(ablation_summary_csv, "w") as f:
        f.write("config,mode,geomean_ratio,geomean_overhead_pct\n")

    ablation_results = {}
    for config_name in CONFIGS.keys():
        ablation_results[config_name] = {}
        for m in MODES:
            ratios_per_bench = []
            for bench in benchmarks:
                bench_name = os.path.splitext(os.path.basename(bench))[0]
                if bench_name == "fib":
                    continue
                u_times = timing_data[(config_name, bench_name, "U")]
                m_times = timing_data[(config_name, bench_name, m)]
                pair_ratios = [mt / ut for mt, ut in zip(m_times, u_times)]
                med_ratio = sorted(pair_ratios)[len(pair_ratios)//2]
                ratios_per_bench.append(med_ratio)

            log_sum = sum(math.log(x) for x in ratios_per_bench)
            geomean = math.exp(log_sum / len(ratios_per_bench))
            ovh = (geomean - 1.0) * 100.0
            ablation_results[config_name][m] = {
                "geomean_ratio": geomean,
                "geomean_overhead_pct": ovh
            }
            with open(ablation_summary_csv, "a") as f:
                f.write(f"{config_name},{m},{geomean:.5f},{ovh:.2f}\n")

    # Save complete JSON
    decomp_json = "results/decomposition_summary.json"
    with open(decomp_json, "w") as f:
        json.dump({
            "decomposition": decomp_records,
            "ablation": ablation_results
        }, f, indent=2)

    print(f"\nDecomposition and ablation experiments finished!")
    print(f"Results written to:\n - {raw_csv}\n - {decomp_summary_csv}\n - {ablation_summary_csv}\n - {decomp_json}")

if __name__ == "__main__":
    run_experiment()
