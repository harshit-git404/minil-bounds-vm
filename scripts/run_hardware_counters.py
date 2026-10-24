#!/usr/bin/env python3
"""
Task 8: Hardware Counters and RDTSC Cycle Analysis.
Probes for hardware performance counters (perf stat).
Documents WSL2 kernel performance counter status.
Collects userspace timestamp counter (RDTSC) cycles for modes U, R, F, N across benchmarks.
"""
import glob
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

VM_DECOMP_GOTO = os.path.join(REPO_ROOT, "vm", "minil-vm-decomp-goto")
VM_DECOMP_SWITCH = os.path.join(REPO_ROOT, "vm", "minil-vm-decomp-switch")
VM_DECOMP_DIRECT = os.path.join(REPO_ROOT, "vm", "minil-vm-decomp-direct")

CONFIGS = {
    "GOTO": VM_DECOMP_GOTO,
    "SWITCH": VM_DECOMP_SWITCH,
    "DIRECT": VM_DECOMP_DIRECT,
}

MODES = ["U", "R", "F", "N"]

def check_perf_counters():
    print("Probing system for Linux perf hardware counters...")
    perf_status = {
        "perf_available": False,
        "hardware_pmu_available": False,
        "kernel_release": os.uname().release,
        "details": ""
    }
    try:
        proc = subprocess.run(["perf", "stat", "ls"], capture_output=True, text=True)
        if "not found for kernel" in proc.stderr or proc.returncode != 0:
            perf_status["details"] = proc.stderr.strip()
        else:
            perf_status["perf_available"] = True
            perf_status["hardware_pmu_available"] = True
    except Exception as e:
        perf_status["details"] = str(e)

    os.makedirs("results", exist_ok=True)
    with open("results/hardware_counters_status.json", "w") as f:
        json.dump(perf_status, f, indent=2)

    print(f"Perf status: available={perf_status['perf_available']}, details={perf_status['details'][:80]}...")
    return perf_status

def collect_rdtsc_cycles():
    print("\nMeasuring userspace RDTSC cycles for modes U, R, F, N...")
    benchmarks = sorted(glob.glob(os.path.join(REPO_ROOT, "benchmarks", "*.minil")))

    raw_csv = "results/rdtsc_cycles.csv"
    with open(raw_csv, "w") as f:
        f.write("config,benchmark,round,mode,cycles,time_ns\n")

    summary_csv = "results/rdtsc_summary.csv"
    with open(summary_csv, "w") as f:
        f.write("config,benchmark,mode,median_cycles,cycle_overhead_pct\n")

    tmp_dir = "/tmp/minil_rdtsc_bins"
    os.makedirs(tmp_dir, exist_ok=True)

    timing_map = {}

    for config_name, vm_bin in CONFIGS.items():
        print(f"Collecting RDTSC on {config_name}...")
        for bench in benchmarks:
            bench_name = os.path.splitext(os.path.basename(bench))[0]
            if bench_name == "fib":
                continue

            # Compile
            mbcs = {}
            for m in MODES:
                mbc_path = os.path.join(tmp_dir, f"{bench_name}_{m}.mbc")
                cmd = ["python3", "-m", "compiler.main", "--mode", m, "-o", mbc_path, bench]
                subprocess.check_call(cmd, cwd=REPO_ROOT)
                mbcs[m] = mbc_path

            # 5 rounds of cycles measurement
            for r in range(5):
                for m in MODES:
                    proc = subprocess.run([vm_bin, mbcs[m]], capture_output=True, text=True, cwd=REPO_ROOT)
                    cycles = None
                    time_ns = None
                    for line in proc.stderr.splitlines():
                        if line.startswith("RDTSC_CYCLES:"):
                            cycles = int(line.split(":")[1].strip())
                        elif line.startswith("TIME_NS:"):
                            time_ns = int(line.split(":")[1].strip())

                    if cycles is not None:
                        with open(raw_csv, "a") as f:
                            f.write(f"{config_name},{bench_name},{r},{m},{cycles},{time_ns}\n")
                        key = (config_name, bench_name, m)
                        if key not in timing_map:
                            timing_map[key] = []
                        timing_map[key].append(cycles)

    # Compute summary
    for config_name in CONFIGS.keys():
        for bench in benchmarks:
            bench_name = os.path.splitext(os.path.basename(bench))[0]
            if bench_name == "fib":
                continue

            u_key = (config_name, bench_name, "U")
            if u_key not in timing_map:
                continue
            u_cycles = sorted(timing_map[u_key])[len(timing_map[u_key]) // 2]

            for m in MODES:
                key = (config_name, bench_name, m)
                med_cycles = sorted(timing_map[key])[len(timing_map[key]) // 2]
                ovh_pct = ((med_cycles - u_cycles) / u_cycles) * 100.0
                with open(summary_csv, "a") as f:
                    f.write(f"{config_name},{bench_name},{m},{med_cycles},{ovh_pct:.2f}\n")

    print(f"RDTSC measurements completed!\n - {raw_csv}\n - {summary_csv}")

def main():
    check_perf_counters()
    collect_rdtsc_cycles()

if __name__ == "__main__":
    main()
