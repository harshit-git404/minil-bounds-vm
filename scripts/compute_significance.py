#!/usr/bin/env python3
"""
scripts/compute_significance.py
Calculates paired statistical significance for headline comparisons:
- Overall suite paired bootstrap 95% CI (excludes 0?)
- Mode vs Mode comparisons (e.g. F vs R, H vs S, N vs R, FN vs F)
- Individual benchmark counts where mode is significantly different from U at 95% CI.
Writes results/significance.csv.
"""

import csv
import math
import random
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMING_RAW = REPO_ROOT / "results" / "timing_raw_1792835669.csv"
DECOMP_RAW = REPO_ROOT / "results" / "decomposition_raw.csv"
OUT_CSV = REPO_ROOT / "results" / "significance.csv"

ARRAY_12 = {
    "bsearch", "bubble", "fill_sum", "gather", "hist", "matmul",
    "matvec_p", "param_sum", "prefix", "rec_sum", "sieve", "stencil_p"
}

def bootstrap_ci_geomean(ratios_by_bench, num_samples=2000, alpha=0.05, seed=42):
    """
    Given dict of bench -> list of paired ratios across rounds,
    resample rounds (or benchmarks) to compute bootstrap 95% CI for the geomean ratio.
    """
    random.seed(seed)
    benchmarks = list(ratios_by_bench.keys())
    num_rounds = len(next(iter(ratios_by_bench.values())))
    
    boot_overheads = []
    for _ in range(num_samples):
        round_indices = [random.randint(0, num_rounds - 1) for _ in range(num_rounds)]
        bench_geomeans = []
        for b in benchmarks:
            sample_ratios = [ratios_by_bench[b][r] for r in round_indices]
            med = sorted(sample_ratios)[len(sample_ratios) // 2]
            bench_geomeans.append(med)
        
        # Geomean across benchmarks
        gm = math.exp(sum(math.log(max(x, 1e-6)) for x in bench_geomeans) / len(bench_geomeans))
        boot_overheads.append((gm - 1.0) * 100.0)

    boot_overheads.sort()
    low = boot_overheads[int(num_samples * (alpha / 2))]
    high = boot_overheads[int(num_samples * (1.0 - alpha / 2))]
    return low, high

def bootstrap_ci_single_bench(ratios, num_samples=2000, alpha=0.05, seed=42):
    random.seed(seed)
    n = len(ratios)
    medians = []
    for _ in range(num_samples):
        resample = [ratios[random.randint(0, n - 1)] for _ in range(n)]
        resample.sort()
        medians.append(resample[n // 2])
    medians.sort()
    low = medians[int(num_samples * (alpha / 2))]
    high = medians[int(num_samples * (1.0 - alpha / 2))]
    return (low - 1.0) * 100.0, (high - 1.0) * 100.0

def main():
    # Load canonical timing data
    # (round, bench, mode) -> time
    timing_data = defaultdict(dict)
    with open(TIMING_RAW) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            m = row["mode"]
            rnd = int(row["round"])
            t = float(row.get("time_s") or row.get("time_sec") or (float(row["time_ns"]) / 1e9))
            timing_data[(b, rnd)][m] = t

    all_benchmarks = sorted(list({b for (b, _) in timing_data.keys() if b != "fib"}))
    original_12 = sorted([b for b in all_benchmarks if b in ARRAY_12])

    # Load decomposition data (GOTO)
    decomp_goto_data = defaultdict(dict)
    with open(DECOMP_RAW) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("dispatch", "GOTO") == "GOTO":
                b = row["benchmark"]
                m = row["mode"]
                rnd = int(row["round"])
                t = float(row["time_sec"]) if "time_sec" in row else float(row["time_ns"]) / 1e9
                decomp_goto_data[(b, rnd)][m] = t

    results = []

    # 1. Headline comparisons vs U
    modes_to_test = ["R", "F", "S", "H", "FS", "FH"]
    
    # We will test on both 22 benchmarks and 12 benchmarks
    for suite_name, benches in [("Combined 22", all_benchmarks), ("Original 12", original_12)]:
        timing_rounds = sorted(list({rnd for (b, rnd) in timing_data.keys() if b == benches[0]}))
        # Count significant benchmarks vs U for each mode
        bench_sig_counts = {}
        for m in modes_to_test:
            sig_count = 0
            for b in benches:
                ratios = []
                for rnd in timing_rounds:
                    t_u = timing_data[(b, rnd)]["U"]
                    t_m = timing_data[(b, rnd)][m]
                    ratios.append(t_m / t_u)
                low_pct, high_pct = bootstrap_ci_single_bench(ratios)
                # Significant if CI excludes 0 (i.e. both > 0 or both < 0)
                if (low_pct > 0 and high_pct > 0) or (low_pct < 0 and high_pct < 0):
                    sig_count += 1
            bench_sig_counts[m] = sig_count

        # Comparisons vs U
        for m in modes_to_test:
            ratios_by_bench = defaultdict(list)
            for b in benches:
                for rnd in timing_rounds:
                    t_u = timing_data[(b, rnd)]["U"]
                    t_m = timing_data[(b, rnd)][m]
                    ratios_by_bench[b].append(t_m / t_u)
            
            # Point estimate geomean
            meds = [sorted(ratios_by_bench[b])[len(ratios_by_bench[b]) // 2] for b in benches]
            gm = math.exp(sum(math.log(x) for x in meds) / len(meds))
            ovh = (gm - 1.0) * 100.0
            ci_low, ci_high = bootstrap_ci_geomean(ratios_by_bench)
            excludes_zero = (ci_low > 0 and ci_high > 0) or (ci_low < 0 and ci_high < 0)

            results.append({
                "suite": suite_name,
                "comparison": f"{m} vs U",
                "mode_a": m,
                "mode_b": "U",
                "geomean_overhead_pct": f"{ovh:+.2f}%",
                "ci_lower_pct": f"{ci_low:+.2f}%",
                "ci_upper_pct": f"{ci_high:+.2f}%",
                "ci_display": f"[{ci_low:+.2f}%, {ci_high:+.2f}%]",
                "excludes_zero_95ci": "YES" if excludes_zero else "NO",
                "statistically_significant": "YES" if excludes_zero else "NO",
                "significant_benchmarks_count": f"{bench_sig_counts[m]} / {len(benches)}",
                "source": "results/timing_raw_1792835669.csv"
            })

        # Pairwise Mode comparisons
        pairwise = [
            ("F", "R"),
            ("H", "S"),
            ("FS", "F"),
            ("FH", "H"),
            ("FH", "FS")
        ]
        for ma, mb in pairwise:
            ratios_by_bench = defaultdict(list)
            for b in benches:
                for rnd in timing_rounds:
                    t_b = timing_data[(b, rnd)][mb]
                    t_a = timing_data[(b, rnd)][ma]
                    ratios_by_bench[b].append(t_a / t_b)
            
            meds = [sorted(ratios_by_bench[b])[len(ratios_by_bench[b]) // 2] for b in benches]
            gm = math.exp(sum(math.log(x) for x in meds) / len(meds))
            ovh = (gm - 1.0) * 100.0
            ci_low, ci_high = bootstrap_ci_geomean(ratios_by_bench)
            excludes_zero = (ci_low > 0 and ci_high > 0) or (ci_low < 0 and ci_high < 0)

            # Count individual benchmarks where ma differs from mb
            sig_cnt = 0
            for b in benches:
                low_p, high_p = bootstrap_ci_single_bench(ratios_by_bench[b])
                if (low_p > 0 and high_p > 0) or (low_p < 0 and high_p < 0):
                    sig_cnt += 1

            results.append({
                "suite": suite_name,
                "comparison": f"{ma} vs {mb}",
                "mode_a": ma,
                "mode_b": mb,
                "geomean_overhead_pct": f"{ovh:+.2f}%",
                "ci_lower_pct": f"{ci_low:+.2f}%",
                "ci_upper_pct": f"{ci_high:+.2f}%",
                "ci_display": f"[{ci_low:+.2f}%, {ci_high:+.2f}%]",
                "excludes_zero_95ci": "YES" if excludes_zero else "NO",
                "statistically_significant": "YES" if excludes_zero else "NO",
                "significant_benchmarks_count": f"{sig_cnt} / {len(benches)}",
                "source": "results/timing_raw_1792835669.csv"
            })

    # Decomposition comparisons: N vs R, F vs R, FN vs F under GOTO (Original 12)
    decomp_pairs = [("N", "R"), ("F", "R"), ("FN", "F")]
    decomp_benches = sorted(list({b for (b, _) in decomp_goto_data.keys() if b != "fib"}))
    decomp_rounds = sorted(list({rnd for (b, rnd) in decomp_goto_data.keys() if b == decomp_benches[0]}))
    for ma, mb in decomp_pairs:
        ratios_by_bench = defaultdict(list)
        for b in decomp_benches:
            for rnd in decomp_rounds:
                t_b = decomp_goto_data[(b, rnd)][mb]
                t_a = decomp_goto_data[(b, rnd)][ma]
                ratios_by_bench[b].append(t_a / t_b)
        
        meds = [sorted(ratios_by_bench[b])[len(ratios_by_bench[b]) // 2] for b in decomp_benches]
        gm = math.exp(sum(math.log(x) for x in meds) / len(meds))
        ovh = (gm - 1.0) * 100.0
        ci_low, ci_high = bootstrap_ci_geomean(ratios_by_bench)
        excludes_zero = (ci_low > 0 and ci_high > 0) or (ci_low < 0 and ci_high < 0)

        sig_cnt = 0
        for b in decomp_benches:
            low_p, high_p = bootstrap_ci_single_bench(ratios_by_bench[b])
            if (low_p > 0 and high_p > 0) or (low_p < 0 and high_p < 0):
                sig_cnt += 1

        results.append({
            "suite": "Original 12 (GOTO Ablation)",
            "comparison": f"{ma} vs {mb}",
            "mode_a": ma,
            "mode_b": mb,
            "geomean_overhead_pct": f"{ovh:+.2f}%",
            "ci_lower_pct": f"{ci_low:+.2f}%",
            "ci_upper_pct": f"{ci_high:+.2f}%",
            "ci_display": f"[{ci_low:+.2f}%, {ci_high:+.2f}%]",
            "excludes_zero_95ci": "YES" if excludes_zero else "NO",
            "statistically_significant": "YES" if excludes_zero else "NO",
            "significant_benchmarks_count": f"{sig_cnt} / {len(decomp_benches)}",
            "source": "results/decomposition_raw.csv"
        })

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "suite", "comparison", "mode_a", "mode_b",
            "geomean_overhead_pct", "ci_lower_pct", "ci_upper_pct", "ci_display",
            "excludes_zero_95ci", "statistically_significant",
            "significant_benchmarks_count", "source"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"Generated {OUT_CSV} with {len(results)} statistical comparisons.")

if __name__ == "__main__":
    main()
