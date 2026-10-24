#!/usr/bin/env python3
"""
Task 11: Vector PDF Figure Generator.
Generates publication-quality vector PDF charts from CSVs only:
1. results/figures/overhead_bars.pdf
2. results/figures/scatter_overhead_instructions.pdf
3. results/figures/static_classification.pdf
4. results/figures/dynamic_checks.pdf
5. results/figures/dispatch_ablation.pdf
6. results/figures/decomposition.pdf
7. results/figures/fault_injection_bars.pdf
"""
import csv
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(REPO_ROOT, "results", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

# Styling
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 13,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

COLORS = {
    "U": "#6c757d",
    "R": "#d9534f",
    "F": "#0275d8",
    "S": "#5cb85c",
    "H": "#5bc0de",
    "FS": "#f0ad4e",
    "FH": "#6f42c1",
    "N": "#e83e8c",
    "FN": "#20c997",
}

def fig_overhead_bars():
    csv_path = os.path.join(REPO_ROOT, "results", "timing_summary.csv")
    if not os.path.exists(csv_path):
        return

    data = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            if b == "fib":
                continue
            m = row["mode"]
            if m not in ["R", "F", "S", "H", "FS", "FH"]:
                continue
            if b not in data:
                data[b] = {}
            ovh = float(row.get("overhead_pct") or row.get("median_overhead_pct", 0.0))
            low = float(row.get("ci_low_pct") or row.get("ci_lower_pct", 0.0))
            high = float(row.get("ci_high_pct") or row.get("ci_upper_pct", 0.0))
            data[b][m] = (ovh, low, high)

    benchmarks = sorted(data.keys())
    modes = ["R", "F", "S", "H", "FS", "FH"]
    n_b = len(benchmarks)
    n_m = len(modes)

    fig, ax = plt.subplots(figsize=(12, 5))
    bar_width = 0.13
    indices = np.arange(n_b)

    for i, m in enumerate(modes):
        x = indices + (i - n_m / 2.0 + 0.5) * bar_width
        y = [data[b].get(m, (0, 0, 0))[0] for b in benchmarks]
        lows = [y[j] - data[b].get(m, (0, 0, 0))[1] for j, b in enumerate(benchmarks)]
        highs = [data[b].get(m, (0, 0, 0))[2] - y[j] for j, b in enumerate(benchmarks)]
        yerr = [np.maximum(0, lows), np.maximum(0, highs)]
        ax.bar(x, y, bar_width, label=f"Mode {m}", color=COLORS[m], yerr=yerr, capsize=2, alpha=0.9)

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right")
    ax.set_ylabel("Execution Time Overhead vs Mode U (%)")
    ax.set_title("Per-Benchmark Bounds Check Overheads with 95% Bootstrap CIs")
    ax.legend(ncol=6, loc="upper right")
    fig.tight_layout()

    out_file = os.path.join(FIG_DIR, "overhead_bars.pdf")
    plt.savefig(out_file)
    plt.close()
    print(f"Generated {out_file}")

def fig_scatter_overhead_instructions():
    timing_path = os.path.join(REPO_ROOT, "results", "timing_summary.csv")
    counts_path = os.path.join(REPO_ROOT, "results", "dynamic_counts.csv")
    if not (os.path.exists(timing_path) and os.path.exists(counts_path)):
        return

    # Map dynamic instruction overhead
    dyn_counts = {}
    with open(counts_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            m = row["mode"]
            if b not in dyn_counts:
                dyn_counts[b] = {}
            dyn_counts[b][m] = float(row["instr_count"])

    dyn_ovh = {}
    for b in dyn_counts:
        u_insn = dyn_counts[b].get("U", 0.0)
        if u_insn > 0:
            dyn_ovh[b] = {}
            for m in ["R", "F", "S", "H", "FS", "FH"]:
                if m in dyn_counts[b]:
                    dyn_ovh[b][m] = (dyn_counts[b][m] - u_insn) / u_insn * 100.0

    x_vals = []
    y_vals = []
    mode_labels = []

    with open(timing_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            m = row["mode"]
            if b == "fib" or m not in ["R", "F", "S", "H", "FS", "FH"]:
                continue
            if b in dyn_ovh and m in dyn_ovh[b]:
                x_vals.append(dyn_ovh[b][m])
                ovh = float(row.get("overhead_pct") or row.get("median_overhead_pct", 0.0))
                y_vals.append(ovh)
                mode_labels.append(m)

    x = np.array(x_vals)
    y = np.array(y_vals)

    # Pearson r and regression line
    r = np.corrcoef(x, y)[0, 1]
    slope, intercept = np.polyfit(x, y, 1)

    fig, ax = plt.subplots(figsize=(7, 5))
    for m in ["R", "F", "S", "H", "FS", "FH"]:
        mask = [lbl == m for lbl in mode_labels]
        ax.scatter(x[mask], y[mask], color=COLORS[m], label=f"Mode {m}", s=40, alpha=0.85, edgecolors="none")

    x_fit = np.linspace(min(x), max(x), 100)
    y_fit = slope * x_fit + intercept
    ax.plot(x_fit, y_fit, color="#333333", linestyle="--", linewidth=1.5,
            label=f"Fit: y = {slope:.2f}x + {intercept:.2f} (r = {r:.2f})")

    ax.set_xlabel("Extra Dynamic Instructions vs Mode U (%)")
    ax.set_ylabel("Measured Execution Time Overhead (%)")
    ax.set_title("Overhead vs Extra Instructions Correlation")
    ax.legend(loc="upper left")
    fig.tight_layout()

    out_file = os.path.join(FIG_DIR, "scatter_overhead_instructions.pdf")
    plt.savefig(out_file)
    plt.close()
    print(f"Generated {out_file}")

def fig_static_classification():
    csv_path = os.path.join(REPO_ROOT, "results", "static_counts.csv")
    if not os.path.exists(csv_path):
        return

    benchmarks = []
    safe = []
    hoisted = []
    residual = []

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            benchmarks.append(b)
            safe.append(int(row["safe_sites"]))
            hoisted.append(int(row["hoisted_sites"]))
            residual.append(int(row["residual_sites"]))

    indices = np.arange(len(benchmarks))
    bar_width = 0.65

    fig, ax = plt.subplots(figsize=(10, 5))
    p1 = ax.bar(indices, safe, bar_width, label="Safe (Interval Analysis, Mode S)", color="#5cb85c")
    p2 = ax.bar(indices, hoisted, bar_width, bottom=safe, label="Hoisted (Loop Guard, Mode H)", color="#5bc0de")
    p3 = ax.bar(indices, residual, bar_width, bottom=np.array(safe) + np.array(hoisted), label="Residual Checks", color="#d9534f")

    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right")
    ax.set_ylabel("Number of Static Array Access Sites")
    ax.set_title("Static Site Classification (Safe vs Hoisted vs Residual)")
    ax.legend(loc="upper right")
    fig.tight_layout()

    out_file = os.path.join(FIG_DIR, "static_classification.pdf")
    plt.savefig(out_file)
    plt.close()
    print(f"Generated {out_file}")

def fig_dynamic_checks():
    csv_path = os.path.join(REPO_ROOT, "results", "dynamic_counts.csv")
    if not os.path.exists(csv_path):
        return

    data = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            m = row["mode"]
            if b not in data:
                data[b] = {}
            data[b][m] = int(row["check_count"])

    benchmarks = sorted([b for b in data.keys() if b != "fib"])
    r_checks = [data[b].get("R", 0) for b in benchmarks]
    s_checks = [data[b].get("S", 0) for b in benchmarks]
    h_checks = [data[b].get("H", 0) for b in benchmarks]
    fh_checks = [data[b].get("FH", 0) for b in benchmarks]

    indices = np.arange(len(benchmarks))
    bar_width = 0.2

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(indices - 1.5*bar_width, r_checks, bar_width, label="Mode R (All Checks)", color=COLORS["R"])
    ax.bar(indices - 0.5*bar_width, s_checks, bar_width, label="Mode S (Safe Eliminated)", color=COLORS["S"])
    ax.bar(indices + 0.5*bar_width, h_checks, bar_width, label="Mode H (Loop Hoisted)", color=COLORS["H"])
    ax.bar(indices + 1.5*bar_width, fh_checks, bar_width, label="Mode FH (Fused + Hoisted)", color=COLORS["FH"])

    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right")
    ax.set_yscale("log")
    ax.set_ylabel("Dynamic Bounds Checks Executed (Log Scale)")
    ax.set_title("Dynamic Bounds Checks Eliminated Across Optimization Modes")
    ax.legend(loc="upper right")
    fig.tight_layout()

    out_file = os.path.join(FIG_DIR, "dynamic_checks.pdf")
    plt.savefig(out_file)
    plt.close()
    print(f"Generated {out_file}")

def fig_dispatch_ablation():
    csv_path = os.path.join(REPO_ROOT, "results", "dispatch_ablation_summary.csv")
    if not os.path.exists(csv_path):
        return

    data = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cfg = row["config"]
            m = row["mode"]
            if cfg not in data:
                data[cfg] = {}
            data[cfg][m] = float(row["geomean_overhead_pct"])

    configs = ["GOTO", "SWITCH", "DIRECT", "OPT3"]
    labels = ["Computed GOTO (-O2)", "Switch Dispatch (-O2)", "Direct-Threaded (-O2)", "GOTO (-O3)"]
    modes = ["R", "F", "S", "H", "N", "FN"]

    indices = np.arange(len(configs))
    bar_width = 0.13

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(modes):
        x = indices + (i - len(modes)/2.0 + 0.5) * bar_width
        y = [data.get(cfg, {}).get(m, 0.0) for cfg in configs]
        ax.bar(x, y, bar_width, label=f"Mode {m}", color=COLORS[m])

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(indices)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Geometric Mean Overhead vs Mode U (%)")
    ax.set_title("Bounds Checking Overhead Across Interpreter Dispatch Architectures")
    ax.legend(ncol=6, loc="upper right")
    fig.tight_layout()

    out_file = os.path.join(FIG_DIR, "dispatch_ablation.pdf")
    plt.savefig(out_file)
    plt.close()
    print(f"Generated {out_file}")

def fig_decomposition():
    csv_path = os.path.join(REPO_ROOT, "results", "decomposition_summary.csv")
    if not os.path.exists(csv_path):
        return

    benchmarks = []
    r_ovh = []
    n_ovh = []
    f_ovh = []
    fn_ovh = []

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["config"] != "GOTO":
                continue
            benchmarks.append(row["benchmark"])
            r_ovh.append(float(row["r_overhead_pct"]))
            n_ovh.append(float(row["n_overhead_pct"]))
            f_ovh.append(float(row["f_overhead_pct"]))
            fn_ovh.append(float(row["fn_overhead_pct"]))

    indices = np.arange(len(benchmarks))
    bar_width = 0.2

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(indices - 1.5*bar_width, r_ovh, bar_width, label="Mode R (Dispatch + Comp)", color=COLORS["R"])
    ax.bar(indices - 0.5*bar_width, n_ovh, bar_width, label="Mode N (Dispatch Only)", color=COLORS["N"])
    ax.bar(indices + 0.5*bar_width, f_ovh, bar_width, label="Mode F (Fused Check)", color=COLORS["F"])
    ax.bar(indices + 1.5*bar_width, fn_ovh, bar_width, label="Mode FN (Fused No-Check)", color=COLORS["FN"])

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right")
    ax.set_ylabel("Execution Time Overhead vs Mode U (%)")
    ax.set_title("Decomposition: Dispatch Overhead (N) vs Comparison vs Fusion (F/FN)")
    ax.legend(ncol=4, loc="upper right")
    fig.tight_layout()

    out_file = os.path.join(FIG_DIR, "decomposition.pdf")
    plt.savefig(out_file)
    plt.close()
    print(f"Generated {out_file}")

def fig_fault_injection_bars():
    csv_path = os.path.join(REPO_ROOT, "results", "fault_injection_results.csv")
    if not os.path.exists(csv_path):
        return

    by_op = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            op = row["operator"]
            if op not in by_op:
                by_op[op] = {"faulty": 0, "benign": 0, "def_viol": 0, "alarms": 0}
            if row.get("classification") == "faulty":
                by_op[op]["faulty"] += 1
            else:
                by_op[op]["benign"] += 1
            finding = row.get("static_finding", "")
            if finding == "definite_violation":
                by_op[op]["def_viol"] += 1
            elif finding == "new_alarm":
                by_op[op]["alarms"] += 1

    ops = sorted(by_op.keys())
    indices = np.arange(len(ops))
    bar_width = 0.2

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(indices - 1.5*bar_width, [by_op[op]["faulty"] for op in ops], bar_width, label="Faulty (Trapped by R)", color="#d9534f")
    ax.bar(indices - 0.5*bar_width, [by_op[op]["benign"] for op in ops], bar_width, label="Benign (In-Bounds)", color="#5cb85c")
    ax.bar(indices + 0.5*bar_width, [by_op[op]["def_viol"] for op in ops], bar_width, label="Definite Compile-Time Violations", color="#6f42c1")
    ax.bar(indices + 1.5*bar_width, [by_op[op]["alarms"] for op in ops], bar_width, label="New Static Alarms", color="#f0ad4e")

    ax.set_xticks(indices)
    ax.set_xticklabels(ops, rotation=25, ha="right")
    ax.set_ylabel("Mutants Tested")
    ax.set_title("Fault Injection Outcomes by Mutation Operator")
    ax.legend(loc="upper right")
    fig.tight_layout()

    out_file = os.path.join(FIG_DIR, "fault_injection_bars.pdf")
    plt.savefig(out_file)
    plt.close()
    print(f"Generated {out_file}")

def main():
    fig_overhead_bars()
    fig_scatter_overhead_instructions()
    fig_static_classification()
    fig_dynamic_checks()
    fig_dispatch_ablation()
    fig_decomposition()
    fig_fault_injection_bars()
    print("All vector PDF figures generated successfully!")

if __name__ == "__main__":
    main()
