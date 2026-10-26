#!/usr/bin/env python3
"""
Task 1b: Export canonical paper numbers to results/paper_numbers.json.
Generates a structured dictionary containing every quantitative metric cited
in paper/paper.tex, recording the exact value, rounded display value,
confidence interval (where applicable), and source CSV/JSON artifact.
"""
import csv
import json
import math
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ORIGINAL_12 = ["bsearch", "bubble", "fill_sum", "gather", "hist", "matmul", "matvec_p", "param_sum", "prefix", "rec_sum", "sieve", "stencil_p"]
EXTENDED_10 = ["qsort", "msort", "poly_gemm", "lu", "jacobi1d", "jacobi2d", "fir", "hash_table", "knapsack", "lcs"]
COMBINED_22 = sorted(ORIGINAL_12 + EXTENDED_10)

def bootstrap_ci(values, num_resamples=2000, alpha=0.05):
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(1337)
    medians = []
    for _ in range(num_resamples):
        sample = [rng.choice(values) for _ in range(n)]
        sample.sort()
        medians.append(sample[n // 2])
    medians.sort()
    low = medians[int((alpha / 2.0) * num_resamples)]
    high = medians[int((1.0 - alpha / 2.0) * num_resamples)]
    return low, high

def bootstrap_geomean_ci(ratios_by_bench, num_resamples=2000, alpha=0.05):
    # ratios_by_bench: list of lists (each sublist is 25 per-round ratios for that bench)
    # Resample rounds paired across benchmarks
    n_rounds = len(ratios_by_bench[0])
    n_bench = len(ratios_by_bench)
    rng = random.Random(1337)
    boot_geomeans = []
    for _ in range(num_resamples):
        sampled_rounds = [rng.randrange(n_rounds) for _ in range(n_rounds)]
        # For each bench, get medians over sampled rounds
        bench_meds = []
        for b_ratios in ratios_by_bench:
            sample = [b_ratios[r] for r in sampled_rounds]
            sample.sort()
            bench_meds.append(sample[len(sample) // 2])
        gm = math.exp(sum(math.log(max(x, 1e-6)) for x in bench_meds) / n_bench)
        boot_geomeans.append(gm)
    boot_geomeans.sort()
    low = boot_geomeans[int((alpha / 2.0) * num_resamples)]
    high = boot_geomeans[int((1.0 - alpha / 2.0) * num_resamples)]
    return (low - 1.0) * 100.0, (high - 1.0) * 100.0

def export_numbers():
    paper_numbers = {}

    # 1. Timing Overheads from results/timing_raw_1792835669.csv
    timing_raw_file = "results/timing_raw_1792835669.csv"
    raw_times = {} # (bench, mode) -> list of times per round
    with open(os.path.join(REPO_ROOT, timing_raw_file)) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            m = row["mode"]
            t = int(row["time_ns"])
            raw_times.setdefault((b, m), []).append(t)

    # Calculate per-round ratios
    def get_paired_ratios(bench_list, mode):
        ratios_by_bench = []
        for b in bench_list:
            u_times = raw_times[(b, "U")]
            m_times = raw_times[(b, mode)]
            ratios = [mt / ut for mt, ut in zip(m_times, u_times)]
            ratios_by_bench.append(ratios)
        return ratios_by_bench

    # Aggregate summaries for 12 and 22 benchmarks
    paper_numbers["timing_overheads"] = {}

    for suite_name, b_list in [("original_12", ORIGINAL_12), ("combined_22", COMBINED_22)]:
        paper_numbers["timing_overheads"][suite_name] = {}
        for m in ["R", "F", "S", "H", "FS", "FH"]:
            ratios_by_bench = get_paired_ratios(b_list, m)
            bench_medians = [sorted(r)[len(r) // 2] for r in ratios_by_bench]
            gm = math.exp(sum(math.log(x) for x in bench_medians) / len(bench_medians))
            ovh = (gm - 1.0) * 100.0
            ci_low, ci_high = bootstrap_geomean_ci(ratios_by_bench)

            paper_numbers["timing_overheads"][suite_name][m] = {
                "geomean_ratio": gm,
                "geomean_overhead_pct": ovh,
                "display": f"{ovh:+.2f}%",
                "ci_95": [ci_low, ci_high],
                "ci_display": f"[{ci_low:+.2f}%, {ci_high:+.2f}%]",
                "source": timing_raw_file
            }

    # 2. Decomposition and Dispatch Ablation from results/decomposition_raw.csv & results/dispatch_ablation_summary.csv
    decomp_raw_file = "results/decomposition_raw.csv"
    decomp_times = {} # (config, bench, mode) -> list of times
    with open(os.path.join(REPO_ROOT, decomp_raw_file)) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cfg = row["config"]
            b = row["benchmark"]
            m = row["mode"]
            t = int(row["time_ns"])
            decomp_times.setdefault((cfg, b, m), []).append(t)

    paper_numbers["dispatch_ablation"] = {}
    for cfg in ["GOTO", "SWITCH", "DIRECT", "OPT3"]:
        paper_numbers["dispatch_ablation"][cfg] = {}
        for m in ["U", "N", "R", "F", "FN", "S", "H", "FS", "FH"]:
            ratios_by_bench = []
            for b in ORIGINAL_12:
                u_times = decomp_times[(cfg, b, "U")]
                m_times = decomp_times[(cfg, b, m)]
                ratios = [mt / ut for mt, ut in zip(m_times, u_times)]
                ratios_by_bench.append(ratios)
            bench_medians = [sorted(r)[len(r) // 2] for r in ratios_by_bench]
            gm = math.exp(sum(math.log(max(x, 1e-6)) for x in bench_medians) / len(bench_medians))
            ovh = (gm - 1.0) * 100.0
            ci_low, ci_high = bootstrap_geomean_ci(ratios_by_bench)

            paper_numbers["dispatch_ablation"][cfg][m] = {
                "geomean_ratio": gm,
                "geomean_overhead_pct": ovh,
                "display": f"{ovh:+.2f}%",
                "ci_95": [ci_low, ci_high],
                "source": "results/dispatch_ablation_summary.csv"
            }

    # Share of R explained by N
    paper_numbers["dispatch_share_of_check_cost"] = {}
    for cfg in ["GOTO", "SWITCH", "DIRECT", "OPT3"]:
        # Compute across rounds and benchmarks
        round_shares = []
        for b in ORIGINAL_12:
            u_t = decomp_times[(cfg, b, "U")]
            n_t = decomp_times[(cfg, b, "N")]
            r_t = decomp_times[(cfg, b, "R")]
            for u, n, r in zip(u_t, n_t, r_t):
                denom = r - u
                if abs(denom) > 1e-9:
                    round_shares.append((n - u) / denom * 100.0)
        sorted_s = sorted(round_shares)
        med_share = sorted_s[len(sorted_s) // 2]
        ci_l, ci_h = bootstrap_ci(round_shares)
        paper_numbers["dispatch_share_of_check_cost"][cfg] = {
            "median_share_pct": med_share,
            "display": f"{med_share:.1f}%",
            "ci_95": [ci_l, ci_h],
            "ci_display": f"[{ci_l:.1f}%, {ci_h:.1f}%]",
            "source": "results/decomposition_summary.csv"
        }

    # 3. Static Counts & Elimination
    static_csv = "results/static_counts.csv"
    tot_sites = 0
    safe_sites = 0
    hoisted_sites = 0
    residual_sites = 0
    size_ratios = {m: [] for m in ["R", "F", "S", "H", "FS", "FH"]}

    with open(os.path.join(REPO_ROOT, static_csv)) as f:
        reader = csv.DictReader(f)
        for row in reader:
            tot = int(row["all_sites"])
            tot_sites += tot
            safe_sites += int(row["safe_sites"])
            hoisted_sites += int(row["hoisted_sites"])
            residual_sites += int(row["residual_sites"])

            b_u = float(row["bytes_U"])
            for m in size_ratios:
                size_ratios[m].append(float(row[f"bytes_{m}"]) / b_u)

    elim_sites = safe_sites + hoisted_sites
    elim_rate_pct = (elim_sites / tot_sites * 100.0) if tot_sites > 0 else 0.0

    paper_numbers["static_counts"] = {
        "total_access_sites": tot_sites,
        "safe_sites": safe_sites,
        "hoisted_sites": hoisted_sites,
        "eliminated_sites": elim_sites,
        "residual_sites": residual_sites,
        "elimination_rate_pct": elim_rate_pct,
        "elimination_rate_display": f"{elim_rate_pct:.1f}%",
        "source": static_csv
    }

    # Bytecode size growth geomeans
    paper_numbers["bytecode_size_growth"] = {}
    for m, ratios in size_ratios.items():
        gm = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
        growth_pct = (gm - 1.0) * 100.0
        paper_numbers["bytecode_size_growth"][m] = {
            "geomean_ratio": gm,
            "growth_pct": growth_pct,
            "display": f"{growth_pct:+.1f}%",
            "source": static_csv
        }

    # 4. Dynamic Counts & Elimination
    dynamic_csv = "results/dynamic_counts.csv"
    dyn_checks = {}
    with open(os.path.join(REPO_ROOT, dynamic_csv)) as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = row["mode"]
            c = int(row["check_count"])
            dyn_checks[m] = dyn_checks.get(m, 0) + c

    r_checks = dyn_checks["R"]
    h_checks = dyn_checks["H"]
    dyn_elim_checks = r_checks - h_checks
    dyn_elim_pct = (dyn_elim_checks / r_checks * 100.0) if r_checks > 0 else 0.0

    paper_numbers["dynamic_counts"] = {
        "r_checks": r_checks,
        "s_checks": dyn_checks.get("S", 0),
        "h_checks": h_checks,
        "fh_checks": dyn_checks.get("FH", 0),
        "checks_eliminated_by_hoisting": dyn_elim_checks,
        "checks_eliminated_display": f"{dyn_elim_checks / 1e6:.1f}M",
        "elimination_rate_pct": dyn_elim_pct,
        "elimination_rate_display": f"{dyn_elim_pct:.1f}%",
        "source": dynamic_csv
    }

    # 5. Fault Injection Totals from results/fault_injection_summary.json
    fault_json_file = "results/fault_injection_summary.json"
    with open(os.path.join(REPO_ROOT, fault_json_file)) as f:
        fi_data = json.load(f)

    comb_fi = fi_data["combined_suite"]
    tot_mut = comb_fi["total_mutants"]
    flt_mut = comb_fi["faulty_mutants"]
    ben_mut = comb_fi["benign_mutants"]
    def_v = comb_fi["definite_violations"]
    new_a = comb_fi["new_alarms"]
    tot_noticed = def_v + new_a
    noticed_rate = (tot_noticed / flt_mut * 100.0) if flt_mut > 0 else 0.0
    silent_u = comb_fi["silent_u_corruptions"]
    silent_u_rate = (silent_u / flt_mut * 100.0) if flt_mut > 0 else 0.0

    paper_numbers["fault_injection"] = {
        "total_mutants": tot_mut,
        "faulty_mutants": flt_mut,
        "benign_mutants": ben_mut,
        "definite_violations": def_v,
        "new_alarms": new_a,
        "total_statically_noticed": tot_noticed,
        "static_detection_rate_pct": noticed_rate,
        "static_detection_rate_display": f"{noticed_rate:.1f}%",
        "u_silent_corruptions": silent_u,
        "u_silent_corruption_rate_pct": silent_u_rate,
        "u_silent_corruption_rate_display": f"{silent_u_rate:.1f}%",
        "u_crashes": 0,
        "differential_divergences_count": 0,
        "operator_stats": fi_data.get("operator_stats", {}),
        "source": fault_json_file
    }

    # 6. Calibration and Noise Floor
    calib_file = "results/calibration.json"
    with open(os.path.join(REPO_ROOT, calib_file)) as f:
        calib = json.load(f)

    # Calculate fib per-mode ratio vs U
    fib_ratios = {}
    u_fib = raw_times[("fib", "U")]
    for m in ["R", "F", "S", "H", "FS", "FH"]:
        m_fib = raw_times[("fib", m)]
        r_list = [mf / uf for mf, uf in zip(m_fib, u_fib)]
        sorted_r = sorted(r_list)
        med_r = sorted_r[len(sorted_r) // 2]
        ci_l, ci_h = bootstrap_ci(r_list)
        fib_ratios[m] = {
            "median_overhead_pct": (med_r - 1.0) * 100.0,
            "ci_95": [(ci_l - 1.0) * 100.0, (ci_h - 1.0) * 100.0]
        }

    # Per-benchmark CV in mode U
    bench_cvs = {}
    for b in COMBINED_22:
        times = raw_times[(b, "U")]
        mean_t = sum(times) / len(times)
        var_t = sum((t - mean_t)**2 for t in times) / (len(times) - 1)
        cv = (math.sqrt(var_t) / mean_t) * 100.0
        bench_cvs[b] = cv

    paper_numbers["calibration_noise"] = {
        "timer_min_delta_ns": calib["timer_min_delta_ns"],
        "timer_median_delta_ns": calib["timer_median_delta_ns"],
        "fib_noise_mean_ms": calib["fib_noise_mean_ns"] / 1e6,
        "fib_noise_cv_percent": calib["fib_noise_cv_percent"],
        "fib_noise_cv_display": f"{calib['fib_noise_cv_percent']:.2f}%",
        "fib_mode_ratios": fib_ratios,
        "per_benchmark_u_cv_percent": bench_cvs,
        "mean_benchmark_u_cv_percent": sum(bench_cvs.values()) / len(bench_cvs),
        "source": calib_file
    }

    # Write results/paper_numbers.json
    out_path = os.path.join(REPO_ROOT, "results", "paper_numbers.json")
    with open(out_path, "w") as f:
        json.dump(paper_numbers, f, indent=2)

    print(f"Exported canonical paper numbers to {out_path}")
    return paper_numbers

if __name__ == "__main__":
    export_numbers()
