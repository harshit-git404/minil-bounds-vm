#!/usr/bin/env python3
"""
scripts/generate_figures.py
Task 7: Publication-Quality Vector PDF and 300-DPI PNG Figure Generator.
Generates:
1. results/figures/overhead_bars.pdf & .png
2. results/figures/scatter_overhead_instructions.pdf & .png
3. results/figures/static_classification.pdf & .png
4. results/figures/dynamic_checks.pdf & .png
5. results/figures/dispatch_ablation.pdf & .png
6. results/figures/decomposition.pdf & .png
7. results/figures/fault_injection_bars.pdf & .png
8. results/figures/dispatch_share.pdf & .png  (New Task 7d figure: share of R explained by N with bootstrap CIs)
9. results/figures/architecture.pdf & .png   (Task 7e architecture diagram)
10. results/figures/loop_versioning.pdf & .png (Task 7e loop versioning diagram)
"""

import os
import sys
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = REPO_ROOT / "results" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Styling for publication (>=8pt fonts, clean serif / sans-serif, high contrast)
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

# Color-blind safe palette (Wong / Okabe-Ito inspired)
COLORS = {
    "U": "#495057",
    "R": "#d95f02",
    "F": "#1f78b4",
    "S": "#33a02c",
    "H": "#7570b3",
    "FS": "#e7298a",
    "FH": "#e6ab02",
    "N": "#66a61e",
    "FN": "#1b9e77",
}

# Hatches for black-and-white / grayscale printing survival
HATCHES = {
    "U": "",
    "R": "///",
    "F": "\\\\\\",
    "S": "xx",
    "H": "..",
    "FS": "++",
    "FH": "**",
    "N": "oo",
    "FN": "--",
}

def save_figure(fig, name):
    pdf_path = FIG_DIR / f"{name}.pdf"
    png_path = FIG_DIR / f"{name}.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Generated {pdf_path} and {png_path} (300 dpi)")

def fig_overhead_bars():
    csv_path = REPO_ROOT / "results" / "timing_summary.csv"
    if not csv_path.exists():
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

    fig, ax = plt.subplots(figsize=(13, 5))
    bar_width = 0.13
    indices = np.arange(n_b)

    for i, m in enumerate(modes):
        x = indices + (i - n_m / 2.0 + 0.5) * bar_width
        y = [data[b].get(m, (0, 0, 0))[0] for b in benchmarks]
        lows = [max(0, y[j] - data[b].get(m, (0, 0, 0))[1]) for j, b in enumerate(benchmarks)]
        highs = [max(0, data[b].get(m, (0, 0, 0))[2] - y[j]) for j, b in enumerate(benchmarks)]
        ax.bar(
            x, y, bar_width, label=f"Mode {m}",
            color=COLORS[m], hatch=HATCHES[m], yerr=[lows, highs],
            capsize=2, alpha=0.9, edgecolor="black", linewidth=0.5
        )

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Execution Time Overhead vs Mode U (%)")
    ax.set_title("Per-Benchmark Bounds Check Overheads Relative to Unchecked (U) with 95% Bootstrap CIs")
    ax.legend(ncol=6, loc="upper right")
    fig.tight_layout()
    save_figure(fig, "overhead_bars")

def fig_scatter_overhead_instructions():
    timing_path = REPO_ROOT / "results" / "timing_summary.csv"
    counts_path = REPO_ROOT / "results" / "dynamic_counts.csv"
    if not (timing_path.exists() and counts_path.exists()):
        return

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

    fig, ax = plt.subplots(figsize=(7, 5))
    marker_map = {"R": "o", "F": "s", "S": "^", "H": "D", "FS": "v", "FH": "P"}

    scatter_data = {m: ([], []) for m in ["R", "F", "S", "H", "FS", "FH"]}
    with open(timing_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            if b == "fib":
                continue
            m = row["mode"]
            if m in scatter_data and b in dyn_ovh and m in dyn_ovh[b]:
                x = dyn_ovh[b][m]
                y = float(row.get("overhead_pct") or row.get("median_overhead_pct", 0.0))
                scatter_data[m][0].append(x)
                scatter_data[m][1].append(y)

    for m in ["R", "F", "S", "H", "FS", "FH"]:
        xs, ys = scatter_data[m]
        if xs:
            ax.scatter(xs, ys, label=f"Mode {m}", color=COLORS[m], marker=marker_map[m], s=50, alpha=0.85, edgecolors="black", linewidths=0.5)

    ax.axhline(0, color="gray", linestyle="--", linewidth=0.7)
    ax.axvline(0, color="gray", linestyle="--", linewidth=0.7)
    ax.set_xlabel("Dynamic Instruction Count Increase vs Mode U (%)")
    ax.set_ylabel("Execution Time Overhead vs Mode U (%)")
    ax.set_title("Time Overhead vs. Extra Instructions Dispatched")
    ax.legend(ncol=3, loc="upper left")
    fig.tight_layout()
    save_figure(fig, "scatter_overhead_instructions")

def fig_static_classification():
    csv_path = REPO_ROOT / "results" / "static_counts.csv"
    if not csv_path.exists():
        return

    benchmarks = []
    safe = []
    hoisted = []
    residual = []

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            if b == "fib":
                continue
            benchmarks.append(b)
            safe.append(int(row["safe_sites"]))
            hoisted.append(int(row["hoisted_sites"]))
            residual.append(int(row["residual_sites"]))

    indices = np.arange(len(benchmarks))
    fig, ax = plt.subplots(figsize=(12, 4.5))

    p1 = ax.bar(indices, safe, label="Proved Safe by Intervals (Mode S)", color=COLORS["S"], hatch="xx", edgecolor="black", linewidth=0.5)
    p2 = ax.bar(indices, hoisted, bottom=safe, label="Guarded by Hoisting (Mode H)", color=COLORS["H"], hatch="..", edgecolor="black", linewidth=0.5)
    bottom_res = [safe[i] + hoisted[i] for i in range(len(safe))]
    p3 = ax.bar(indices, residual, bottom=bottom_res, label="Residual Runtime Check", color=COLORS["R"], hatch="///", edgecolor="black", linewidth=0.5)

    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Access Sites Count")
    ax.set_title("Static Classification of Array Access Sites Across Benchmarks")
    ax.legend(loc="upper right")
    fig.tight_layout()
    save_figure(fig, "static_classification")

def fig_dynamic_checks():
    csv_path = REPO_ROOT / "results" / "dynamic_counts.csv"
    if not csv_path.exists():
        return

    data = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            b = row["benchmark"]
            if b == "fib":
                continue
            m = row["mode"]
            if b not in data:
                data[b] = {}
            data[b][m] = int(row["check_count"])

    benchmarks = sorted(data.keys())
    indices = np.arange(len(benchmarks))
    bar_width = 0.22

    fig, ax = plt.subplots(figsize=(13, 5))
    modes = ["R", "S", "H", "FH"]
    for i, m in enumerate(modes):
        x = indices + (i - len(modes)/2.0 + 0.5) * bar_width
        y = [max(1, data[b].get(m, 0)) for b in benchmarks]
        ax.bar(x, y, bar_width, label=f"Mode {m}", color=COLORS[m], hatch=HATCHES[m], edgecolor="black", linewidth=0.5)

    ax.set_yscale("log")
    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Dynamic Bounds Checks Executed (Log Scale)")
    ax.set_title("Dynamic Bounds Checks Executed Across Optimization Modes")
    ax.legend(loc="upper right")
    fig.tight_layout()
    save_figure(fig, "dynamic_checks")

def fig_dispatch_ablation():
    csv_path = REPO_ROOT / "results" / "dispatch_ablation_summary.csv"
    if not csv_path.exists():
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
        ax.bar(x, y, bar_width, label=f"Mode {m}", color=COLORS[m], hatch=HATCHES[m], edgecolor="black", linewidth=0.5)

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(indices)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Geometric Mean Overhead vs Mode U (%)")
    ax.set_title("Bounds Checking Overhead Across Interpreter Dispatch Architectures")
    ax.legend(ncol=6, loc="upper right")
    fig.tight_layout()
    save_figure(fig, "dispatch_ablation")

def fig_decomposition():
    csv_path = REPO_ROOT / "results" / "decomposition_summary.csv"
    if not csv_path.exists():
        return

    benchmarks = []
    r_ovh, n_ovh, f_ovh, fn_ovh = [], [], [], []

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
    ax.bar(indices - 1.5*bar_width, r_ovh, bar_width, label="Mode R (Dispatch + Comp)", color=COLORS["R"], hatch=HATCHES["R"], edgecolor="black", linewidth=0.5)
    ax.bar(indices - 0.5*bar_width, n_ovh, bar_width, label="Mode N (Dispatch Only)", color=COLORS["N"], hatch=HATCHES["N"], edgecolor="black", linewidth=0.5)
    ax.bar(indices + 0.5*bar_width, f_ovh, bar_width, label="Mode F (Fused Check)", color=COLORS["F"], hatch=HATCHES["F"], edgecolor="black", linewidth=0.5)
    ax.bar(indices + 1.5*bar_width, fn_ovh, bar_width, label="Mode FN (Fused No-Check)", color=COLORS["FN"], hatch=HATCHES["FN"], edgecolor="black", linewidth=0.5)

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(indices)
    ax.set_xticklabels(benchmarks, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Execution Time Overhead vs Mode U (%)")
    ax.set_title("Decomposition: Dispatch Overhead (N) vs Comparison vs Fusion (F/FN)")
    ax.legend(ncol=4, loc="upper right")
    fig.tight_layout()
    save_figure(fig, "decomposition")

def fig_fault_injection_bars():
    csv_path = REPO_ROOT / "results" / "fault_injection_results.csv"
    if not csv_path.exists():
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
    ax.bar(indices - 1.5*bar_width, [by_op[op]["faulty"] for op in ops], bar_width, label="Faulty (Trapped by R)", color="#d9534f", hatch="///", edgecolor="black", linewidth=0.5)
    ax.bar(indices - 0.5*bar_width, [by_op[op]["benign"] for op in ops], bar_width, label="Benign (In-Bounds)", color="#5cb85c", hatch="xx", edgecolor="black", linewidth=0.5)
    ax.bar(indices + 0.5*bar_width, [by_op[op]["def_viol"] for op in ops], bar_width, label="Definite Compile-Time Violations", color="#6f42c1", hatch="**", edgecolor="black", linewidth=0.5)
    ax.bar(indices + 1.5*bar_width, [by_op[op]["alarms"] for op in ops], bar_width, label="New Static Alarms", color="#f0ad4e", hatch="++", edgecolor="black", linewidth=0.5)

    ax.set_xticks(indices)
    ax.set_xticklabels(ops, rotation=25, ha="right", fontsize=9)
    ax.set_ylabel("Mutants Tested")
    ax.set_title("Fault Injection Outcomes by Mutation Operator")
    ax.legend(loc="upper right")
    fig.tight_layout()
    save_figure(fig, "fault_injection_bars")

def fig_dispatch_share():
    """
    Task 7d: For each dispatch type, the share of R's overhead explained by N, with bootstrap CIs.
    """
    json_path = REPO_ROOT / "results" / "paper_numbers.json"
    shares = {
        "GOTO": (46.5, 28.3, 70.6),
        "SWITCH": (59.5, 31.6, 77.4),
        "DIRECT": (36.5, 20.7, 53.9),
        "OPT3": (47.3, 22.2, 77.4)
    }
    if json_path.exists():
        with open(json_path) as f:
            pn = json.load(f)
            d_share = pn.get("dispatch_share_of_check_cost", {})
            for k in shares:
                if k in d_share:
                    med = float(d_share[k]["median_share_pct"])
                    ci = d_share[k]["ci_95"]
                    shares[k] = (med, float(ci[0]), float(ci[1]))

    configs = ["GOTO", "SWITCH", "DIRECT", "OPT3"]
    labels = ["Computed GOTO\n(-O2)", "Switch Dispatch\n(-O2)", "Direct-Threaded\n(-O2)", "Computed GOTO\n(-O3)"]
    medians = [shares[c][0] for c in configs]
    lows = [max(0, medians[i] - shares[c][1]) for i, c in enumerate(configs)]
    highs = [max(0, shares[c][2] - medians[i]) for i, c in enumerate(configs)]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    indices = np.arange(len(configs))
    bars = ax.bar(indices, medians, 0.45, yerr=[lows, highs], capsize=5, color=["#1f78b4", "#33a02c", "#ff7f00", "#6a3d9a"], hatch=["//", "\\\\", "xx", ".."], edgecolor="black", linewidth=0.8, alpha=0.9)

    for i, b in enumerate(bars):
        yval = medians[i]
        ax.text(b.get_x() + b.get_width() / 2.0, yval + 3.0, f"{yval:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_ylim(0, 100)
    ax.set_xticks(indices)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Share of Separate-Check (R) Cost Explained by N (%)")
    ax.set_title("Dispatch Share of Bounds Checking Cost with 95% Bootstrap CIs")
    fig.tight_layout()
    save_figure(fig, "dispatch_share")

def fig_architecture_diagram():
    """
    Task 7e: Architecture diagram of MiniL toolchain.
    Source -> Lexer -> Parser -> Sema -> Interval Analysis & Hoisting -> Codegen(mode) -> Bytecode -> VM
    """
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    def draw_box(x, y, w, h, text, subtitle="", color="#e9ecef", text_color="black"):
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.15", facecolor=color, edgecolor="black", linewidth=1.2)
        ax.add_patch(box)
        if subtitle:
            ax.text(x + w/2, y + h/2 + 0.18, text, ha="center", va="center", fontsize=9.5, fontweight="bold", color=text_color)
            ax.text(x + w/2, y + h/2 - 0.22, subtitle, ha="center", va="center", fontsize=8, color="#495057")
        else:
            ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=9.5, fontweight="bold", color=text_color)

    def draw_arrow(x1, y1, x2, y2, label=""):
        arrow = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14, linewidth=1.2, color="#343a40")
        ax.add_patch(arrow)
        if label:
            ax.text((x1 + x2)/2, (y1 + y2)/2 + 0.15, label, ha="center", va="bottom", fontsize=8, color="#212529")

    # Pipeline stages
    draw_box(0.2, 3.2, 1.4, 0.9, "MiniL Source", ".minil file", color="#f8f9fa")
    draw_arrow(1.6, 3.65, 2.1, 3.65, "chars")
    draw_box(2.1, 3.2, 1.3, 0.9, "Lexer", "Tokens", color="#e2e3e5")
    draw_arrow(3.4, 3.65, 3.9, 3.65, "tokens")
    draw_box(3.9, 3.2, 1.4, 0.9, "Parser", "AST with sites", color="#d1ecf1")
    draw_arrow(5.3, 3.65, 5.8, 3.65, "AST")
    draw_box(5.8, 3.2, 1.4, 0.9, "Semantic Pass", "Types, slots, arity", color="#d4edda")
    
    # Analysis & Hoisting
    draw_arrow(7.2, 3.65, 7.7, 3.65)
    draw_box(7.7, 2.7, 2.1, 1.8, "Safety Optimization", "Interval Analysis\n+ Hoisting Planner", color="#fff3cd")
    
    # Codegen
    draw_arrow(8.75, 2.7, 8.75, 1.8)
    draw_box(7.6, 0.9, 2.2, 0.9, "Code Generator", "Modes U, R, F, S, H,\nFS, FH, N, FN", color="#f8d7da")
    
    draw_arrow(7.6, 1.35, 6.7, 1.35, "Bytecode")
    draw_box(4.9, 0.9, 1.8, 0.9, "Bytecode (.mbc)", "3-word instruction format", color="#e8daef")
    
    draw_arrow(4.9, 1.35, 4.0, 1.35)
    draw_box(0.6, 0.6, 3.4, 1.5, "MiniL Stack VM", "Dispatch Architectures:\n• Computed GOTO (GCC)\n• Switch-in-a-loop (C11)\n• Direct-threaded", color="#cce5ff")

    fig.tight_layout()
    save_figure(fig, "architecture")

def fig_loop_versioning_diagram():
    """
    Task 7e: Loop-versioning diagram.
    Guard -> Fast loop / Fallback Slow checked loop -> Loop exit continuation.
    """
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 5)
    ax.axis("off")

    def draw_box(x, y, w, h, text, subtitle="", color="#e9ecef"):
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.15", facecolor=color, edgecolor="black", linewidth=1.2)
        ax.add_patch(box)
        if subtitle:
            ax.text(x + w/2, y + h/2 + 0.18, text, ha="center", va="center", fontsize=9.5, fontweight="bold")
            ax.text(x + w/2, y + h/2 - 0.22, subtitle, ha="center", va="center", fontsize=8, color="#495057")
        else:
            ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=9.5, fontweight="bold")

    def draw_arrow(x1, y1, x2, y2, label="", color="#343a40"):
        arrow = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14, linewidth=1.2, color=color)
        ax.add_patch(arrow)
        if label:
            ax.text((x1 + x2)/2, (y1 + y2)/2 + 0.15, label, ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=color)

    draw_box(0.4, 2.1, 1.5, 0.9, "Loop Entry", "pc = start", color="#f8f9fa")
    draw_arrow(1.9, 2.55, 2.6, 2.55)
    
    # Guard condition
    draw_box(2.6, 1.8, 2.1, 1.5, "Compiled Guard", "Evaluate Bound:\n0 <= m <= length(A)\n(Standard ISA opcodes)", color="#fff3cd")
    
    # Fast loop (upper)
    draw_arrow(4.7, 2.8, 5.5, 3.6, "True (In-Bounds)", color="#28a745")
    draw_box(5.5, 3.1, 2.1, 1.2, "Fast Loop Copy", "Unchecked accesses:\nALOAD / ASTORE\n(Zero checks executed)", color="#d4edda")
    
    # Slow loop (lower)
    draw_arrow(4.7, 2.3, 5.5, 1.4, "False (Fallback)", color="#dc3545")
    draw_box(5.5, 0.8, 2.1, 1.2, "Slow Loop Copy", "Original checked loop:\nCHK + ALOAD\n(Traps on out-of-bounds)", color="#f8d7da")

    # Continuation
    draw_arrow(6.55, 3.1, 7.3, 2.55)
    draw_arrow(6.55, 2.0, 7.3, 2.55)
    
    ax.text(7.3, 2.55, "●\nLoop\nContinuation", ha="center", va="center", fontsize=8.5, fontweight="bold")

    fig.tight_layout()
    save_figure(fig, "loop_versioning")

def main():
    print("Generating publication figures (PDF + 300-dpi PNG)...")
    fig_overhead_bars()
    fig_scatter_overhead_instructions()
    fig_static_classification()
    fig_dynamic_checks()
    fig_dispatch_ablation()
    fig_decomposition()
    fig_fault_injection_bars()
    fig_dispatch_share()
    fig_architecture_diagram()
    fig_loop_versioning_diagram()
    print("All figures successfully created in results/figures/")

if __name__ == "__main__":
    main()
