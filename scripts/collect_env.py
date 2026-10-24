#!/usr/bin/env python3
import json
import os
import platform
import subprocess
import sys

def get_cpu_model():
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    try:
        out = subprocess.check_output(["lscpu"], text=True)
        for line in out.splitlines():
            if "Model name:" in line:
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "Unknown CPU"

def get_kernel():
    return platform.platform() or subprocess.check_output(["uname", "-a"], text=True).strip()

def get_gcc_version():
    try:
        out = subprocess.check_output(["gcc", "--version"], text=True)
        return out.splitlines()[0].strip()
    except Exception as e:
        return f"gcc unavailable: {e}"

def get_governor():
    for p in ["/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "/sys/devices/system/cpu/scaling_governor"]:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
    return "not available / virtualized"

def get_core_pinning():
    try:
        out = subprocess.check_output(["taskset", "-p", str(os.getpid())], text=True).strip()
        return out
    except Exception as e:
        return f"unpinned: {e}"

def get_git_commit():
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        return out
    except Exception as e:
        return f"unknown: {e}"

def collect_env(out_path="results/env.json", extra_flags="-O2 -std=c11"):
    env_data = {
        "cpu_model": get_cpu_model(),
        "os_kernel": get_kernel(),
        "gcc_version": get_gcc_version(),
        "gcc_flags": extra_flags,
        "governor": get_governor(),
        "core_pinning": get_core_pinning(),
        "git_commit": get_git_commit()
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(env_data, f, indent=2)
    print(f"Recorded environment in {out_path}")
    return env_data

if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "results/env.json"
    flags = sys.argv[2] if len(sys.argv) > 2 else "-O2 -std=c11"
    collect_env(out_file, flags)
