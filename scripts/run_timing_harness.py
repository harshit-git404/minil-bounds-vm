#!/usr/bin/env python3
"""
Reproducible Timing and Counting Harness for MiniL Benchmarks (Task 4).
Runs 25 measurement rounds (after 1 discarded warm-up round) with paired,
interleaved, randomly shuffled execution on a pinned CPU core (taskset).
Calculates per-round ratios T_mode / T_U, median overhead %, and 95%
percentile bootstrap confidence intervals (2000 resamples).
Computes static site counts, dynamic instruction/check counts, and bytecode sizes.
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

VM_DEFAULT = os.path.join(REPO_ROOT, "vm", "minil-vm")
VM_COUNT = os.path.join(REPO_ROOT, "vm", "minil-vm-count")

MODES = ["U", "R", "F", "S", "H", "FS", "FH"]
ROUNDS = 25 # measurement rounds (plus 1 warm-up round)
BOOTSTRAP_RESAMPLES = 2000

def get_pinned_cmd(cmd):
    # If taskset is available, pin to core 0
    try:
        subprocess.check_call(["which", "taskset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ["taskset", "-c", "0"] + cmd
    except Exception:
        return cmd

def calibrate_timer():
    print("Running timer resolution calibration...")
    deltas = []
    for _ in range(5000):
        t1 = time.perf_counter_ns()
        t2 = time.perf_counter_ns()
        d = t2 - t1
        if d > 0:
            deltas.append(d)
    min_delta = min(deltas) if deltas else 1
    med_delta = sorted(deltas)[len(deltas)//2] if deltas else 1

    # Measure no-op noise using fib control benchmark
    fib_mbc = "/tmp/calib_fib.mbc"
    subprocess.check_call(["python3", "-m", "compiler.main", "--mode", "U", "-o", fib_mbc, "benchmarks/fib.minil"], cwd=REPO_ROOT)
    fib_times = []
    for _ in range(25):
        proc = subprocess.run(get_pinned_cmd([VM_DEFAULT, fib_mbc]), capture_output=True, text=True, cwd=REPO_ROOT)
        for l in proc.stderr.splitlines():
            if l.startswith("TIME_NS:"):
                fib_times.append(int(l.split(":")[1].strip()))
    if os.path.exists(fib_mbc):
        os.remove(fib_mbc)

    mean_fib = sum(fib_times) / len(fib_times)
    var_fib = sum((x - mean_fib)**2 for x in fib_times) / (len(fib_times) - 1)
    std_fib = math.sqrt(var_fib)
    cv_fib = (std_fib / mean_fib) * 100.0

    calib = {
        "timer_min_delta_ns": min_delta,
        "timer_median_delta_ns": med_delta,
        "fib_noise_mean_ns": mean_fib,
        "fib_noise_std_ns": std_fib,
        "fib_noise_cv_percent": cv_fib
    }
    with open("results/calibration.json", "w") as f:
        json.dump(calib, f, indent=2)
    print(f"Calibration complete: timer min delta = {min_delta} ns, fib noise CV = {cv_fib:.2f}%")
    return calib

def bootstrap_ci(ratios, num_resamples=BOOTSTRAP_RESAMPLES, alpha=0.05):
    n = len(ratios)
    boot_medians = []
    rng = random.Random(1337)
    for _ in range(num_resamples):
        sample = [rng.choice(ratios) for _ in range(n)]
        sample.sort()
        boot_medians.append(sample[n // 2])
    boot_medians.sort()
    low_idx = int((alpha / 2.0) * num_resamples)
    high_idx = int((1.0 - alpha / 2.0) * num_resamples)
    return boot_medians[low_idx], boot_medians[high_idx]

def collect_static_and_dynamic_counts(benchmarks):
    print("\nCollecting static counts, bytecode sizes, and dynamic instruction/check counts...")
    from compiler.lexer import Lexer
    from compiler.parser import Parser
    from compiler.sema import Sema
    from compiler.analysis import IntervalAnalysis
    from compiler.hoisting import HoistingPlanner

    static_rows = [["benchmark", "all_sites", "safe_sites", "hoisted_sites", "residual_sites", "bytes_U", "bytes_R", "bytes_F", "bytes_S", "bytes_H", "bytes_FS", "bytes_FH"]]
    dynamic_rows = [["benchmark", "mode", "instr_count", "check_count"]]

    for b_path in benchmarks:
        name = os.path.splitext(os.path.basename(b_path))[0]
        with open(b_path, "r") as f:
            code = f.read()

        # Static analysis
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        sema.analyze(ast)
        ana = IntervalAnalysis(sema)
        rep = ana.analyze(ast)

        all_sites = rep["summary"]["total_sites"]
        safe_sites = rep["summary"]["safe"]

        planner = HoistingPlanner(sema)
        hoist_res = planner.plan_and_transform(ast, ana.get_safe_sites())
        hoisted_sites = len(hoist_res.hoisted_sites)
        residual_sites = all_sites - safe_sites - hoisted_sites

        # Bytecode sizes
        sizes = {}
        for m in MODES:
            mbc_file = f"/tmp/count_{name}_{m}.mbc"
            subprocess.check_call(["python3", "-m", "compiler.main", "--mode", m, "-o", mbc_file, b_path], cwd=REPO_ROOT)
            sizes[m] = os.path.getsize(mbc_file)

            # Dynamic counts from VM_COUNT
            proc = subprocess.run(get_pinned_cmd([VM_COUNT, mbc_file]), capture_output=True, text=True, cwd=REPO_ROOT)
            instr_c = 0
            check_c = 0
            for l in proc.stderr.splitlines():
                if l.startswith("INSTR_COUNT:"):
                    instr_c = int(l.split(":")[1].strip())
                elif l.startswith("CHECK_COUNT:"):
                    check_c = int(l.split(":")[1].strip())
            dynamic_rows.append([name, m, str(instr_c), str(check_c)])

            if os.path.exists(mbc_file):
                os.remove(mbc_file)

        static_rows.append([
            name, str(all_sites), str(safe_sites), str(hoisted_sites), str(residual_sites),
            str(sizes["U"]), str(sizes["R"]), str(sizes["F"]), str(sizes["S"]),
            str(sizes["H"]), str(sizes["FS"]), str(sizes["FH"])
        ])

    with open("results/static_counts.csv", "w") as f:
        for r in static_rows:
            f.write(",".join(r) + "\n")

    with open("results/dynamic_counts.csv", "w") as f:
        for r in dynamic_rows:
            f.write(",".join(r) + "\n")

    print("Static counts written to results/static_counts.csv")
    print("Dynamic counts written to results/dynamic_counts.csv")

def run_timing_experiment(benchmarks):
    print(f"\nRunning paired interleaved timing harness: {ROUNDS} rounds, pinned core...")
    os.makedirs("results", exist_ok=True)
    timestamp = int(time.time())
    raw_csv_path = f"results/timing_raw_{timestamp}.csv"

    # Pre-compile bytecode files for all benchmarks and modes
    mbc_files = {}
    for b_path in benchmarks:
        name = os.path.splitext(os.path.basename(b_path))[0]
        mbc_files[name] = {}
        for m in MODES:
            mbc_path = f"/tmp/{name}_{m}.mbc"
            subprocess.check_call(["python3", "-m", "compiler.main", "--mode", m, "-o", mbc_path, b_path], cwd=REPO_ROOT)
            mbc_files[name][m] = mbc_path

    rng = random.Random(42)

    raw_records = []
    # Structure: per_benchmark[name][mode] = list of time_ns
    per_round_times = {name: {m: [] for m in MODES} for name in mbc_files}

    # 1 warm-up round (discarded) + ROUNDS measurement rounds
    total_rounds = ROUNDS + 1

    for round_idx in range(total_rounds):
        is_warmup = (round_idx == 0)
        print(f"  Round {round_idx}/{ROUNDS} {'(warm-up, discarded)' if is_warmup else ''}...")

        # Benchmark order shuffled
        b_names = list(mbc_files.keys())
        rng.shuffle(b_names)

        for name in b_names:
            # Modes shuffled within each round
            modes_order = list(MODES)
            rng.shuffle(modes_order)

            for m in modes_order:
                mbc = mbc_files[name][m]
                proc = subprocess.run(get_pinned_cmd([VM_DEFAULT, mbc]), capture_output=True, text=True, cwd=REPO_ROOT)
                if proc.returncode != 0:
                    print(f"FATAL: Benchmark {name} failed in mode {m}: {proc.stderr}")
                    sys.exit(1)

                t_ns = None
                for line in proc.stderr.splitlines():
                    if line.startswith("TIME_NS:"):
                        t_ns = int(line.split(":")[1].strip())
                        break

                if t_ns is None:
                    raise RuntimeError(f"Could not extract TIME_NS for {name} mode {m}")

                if not is_warmup:
                    raw_records.append({
                        "round": round_idx,
                        "benchmark": name,
                        "mode": m,
                        "time_ns": t_ns,
                        "time_s": t_ns / 1e9
                    })
                    per_round_times[name][m].append(t_ns)

    # Save raw results
    with open(raw_csv_path, "w") as f:
        f.write("round,benchmark,mode,time_ns,time_s\n")
        for rec in raw_records:
            f.write(f"{rec['round']},{rec['benchmark']},{rec['mode']},{rec['time_ns']},{rec['time_s']:.9f}\n")
    print(f"Raw timings saved to {raw_csv_path}")

    # Clean up temporary mbc files
    for name in mbc_files:
        for m in MODES:
            if os.path.exists(mbc_files[name][m]):
                os.remove(mbc_files[name][m])

    # Compute paired ratios and bootstrap CIs
    summary_rows = [["benchmark", "mode", "overhead_pct", "ci_low_pct", "ci_high_pct", "median_ratio"]]
    benchmark_medians = {m: [] for m in MODES if m != "U"}

    for name in sorted(mbc_files.keys()):
        t_u_list = per_round_times[name]["U"]
        for m in MODES:
            if m == "U":
                summary_rows.append([name, "U", "0.0", "0.0", "0.0", "1.0"])
                continue

            t_m_list = per_round_times[name][m]
            ratios = [t_m / t_u for t_m, t_u in zip(t_m_list, t_u_list)]
            sorted_r = sorted(ratios)
            med_ratio = sorted_r[len(sorted_r) // 2]
            ci_low, ci_high = bootstrap_ci(ratios)

            overhead = (med_ratio - 1.0) * 100.0
            ci_low_pct = (ci_low - 1.0) * 100.0
            ci_high_pct = (ci_high - 1.0) * 100.0

            summary_rows.append([
                name, m,
                f"{overhead:+.2f}",
                f"{ci_low_pct:+.2f}",
                f"{ci_high_pct:+.2f}",
                f"{med_ratio:.4f}"
            ])

            if name != "fib":
                benchmark_medians[m].append(med_ratio)

    with open("results/timing_summary.csv", "w") as f:
        for r in summary_rows:
            f.write(",".join(r) + "\n")
    print("Summary written to results/timing_summary.csv")

    ORIGINAL_13 = {"bsearch", "bubble", "fib", "fill_sum", "gather", "hist", "matmul", "matvec_p", "param_sum", "prefix", "rec_sum", "sieve", "stencil_p"}
    EXTENDED_10 = {"qsort", "msort", "poly_gemm", "lu", "jacobi1d", "jacobi2d", "fir", "hash_table", "knapsack", "lcs"}

    # Compute geomeans for: original (excl fib), extended, and combined
    def compute_geomean(bench_list):
        res = {}
        for m in [m for m in MODES if m != "U"]:
            vals = []
            for b_name in bench_list:
                if b_name == "fib" or b_name not in per_round_times:
                    continue
                t_u_list = per_round_times[b_name]["U"]
                t_m_list = per_round_times[b_name][m]
                ratios = [tm / tu for tm, tu in zip(t_m_list, t_u_list)]
                vals.append(sorted(ratios)[len(ratios)//2])
            if vals:
                log_sum = sum(math.log(v) for v in vals)
                gm = math.exp(log_sum / len(vals))
                res[m] = {
                    "geomean_ratio": gm,
                    "geomean_overhead_pct": (gm - 1.0) * 100.0
                }
        return res

    orig_benchmarks = [b for b in ORIGINAL_13 if b != "fib"]
    ext_benchmarks = list(EXTENDED_10)
    comb_benchmarks = [b for b in set(orig_benchmarks + ext_benchmarks) if b in per_round_times]

    aggregates = {
        "original_13": compute_geomean(orig_benchmarks),
        "extended_10": compute_geomean(ext_benchmarks),
        "combined_suite": compute_geomean(comb_benchmarks)
    }

    print("\n--- Geometric Mean Overhead: Original 12 Array Benchmarks ---")
    for m, d in aggregates["original_13"].items():
        print(f"Mode {m:2s}: ratio = {d['geomean_ratio']:.4f} ({d['geomean_overhead_pct']:+.2f}%)")

    print("\n--- Geometric Mean Overhead: Extended 10 Benchmarks ---")
    for m, d in aggregates["extended_10"].items():
        print(f"Mode {m:2s}: ratio = {d['geomean_ratio']:.4f} ({d['geomean_overhead_pct']:+.2f}%)")

    print("\n--- Geometric Mean Overhead: Combined Suite (22 Array Benchmarks) ---")
    for m, d in aggregates["combined_suite"].items():
        print(f"Mode {m:2s}: ratio = {d['geomean_ratio']:.4f} ({d['geomean_overhead_pct']:+.2f}%)")

    with open("results/aggregate_summary.json", "w") as f:
        json.dump(aggregates, f, indent=2)
    print("\nAggregate summary written to results/aggregate_summary.json")

def main():
    collect_env("results/env.json")
    calibrate_timer()

    benchmarks = sorted(glob.glob("benchmarks/*.minil"))
    if len(benchmarks) < 13:
        raise RuntimeError(f"Expected at least 13 benchmarks, found {len(benchmarks)}")

    collect_static_and_dynamic_counts(benchmarks)
    run_timing_experiment(benchmarks)

if __name__ == "__main__":
    main()
