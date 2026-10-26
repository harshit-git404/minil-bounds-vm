# Running MiniL on Native Windows (MSYS2 UCRT64)

This document provides exact, copy-paste instructions for building and running the MiniL compiler, virtual machine, and benchmark timing suite natively on Windows 10/11 using the modern **MSYS2 UCRT64** toolchain or native **PowerShell**.

---

## 1. Prerequisites & Environment Setup

1. **Install MSYS2**:
   Download and run the installer from [https://www.msys2.org/](https://www.msys2.org/). Default path is `C:\msys64`.

2. **Open the UCRT64 Terminal**:
   Launch `MSYS2 UCRT64` from the Windows Start menu (or run `C:\msys64\ucrt64.exe`).

3. **Install GCC, Python, Make, and Git**:
   Run the following command inside the UCRT64 terminal:
   ```bash
   pacman -Syu --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-python make git
   ```

4. **Verify Toolchain**:
   ```bash
   gcc --version       # GCC 13+ with UCRT runtime
   python3 --version   # Python 3.11+
   make --version
   ```

---

## 2. Clone and Build MiniL Binaries

From inside the MSYS2 UCRT64 terminal:

```bash
git clone https://github.com/harshit-git404/minil-bounds-vm.git
cd minil-bounds-vm

# Build all Windows VM binaries (.exe)
bash scripts/build_windows.sh
```

This compiles:
- `vm/minil-vm-goto.exe`: Computed `goto` indirect-threaded dispatch (default VM)
- `vm/minil-vm-switch.exe`: Standard C `switch` statement dispatch
- `vm/minil-vm-direct.exe`: Direct-threaded dispatch
- `vm/minil-vm-count.exe`: Instruction and bounds-check instrumentation build
- `vm/minil-vm-decomp-goto.exe`: Decomposition build supporting `NOPCHK`, `ALOADN`, `ASTOREN`
- `vm/minil-vm-opt3.exe`: `-O3` optimized build

---

## 3. Running Tests and Benchmarks

### Option A: Using MSYS2 Bash

To execute the paired, interleaved timing suite (25 rounds, core affinity):
```bash
bash scripts/run_windows.sh
```

### Option B: Using Native Windows PowerShell

Open Windows PowerShell (Run as Administrator or standard user with script execution rights):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd C:\path\to\minil-bounds-vm

# Run native PowerShell harness with Core 0 CPU affinity
.\scripts\run_windows.ps1
```

---

## 4. Output Artifacts and Schema Consistency

All output artifacts are saved directly to the `results/` directory, adhering strictly to the canonical repository schema:

1. **Raw Timing Measurements**:
   - Path: `results/timing_raw_windows.csv`
   - Schema: `round,benchmark,mode,time_ns,time_s`
   - Description: Per-round monotonic interpreter loop execution time in nanoseconds and seconds across 25 paired rounds.

2. **Summary Timing Statistics**:
   - Path: `results/timing_summary_windows.csv`
   - Schema: `benchmark,mode,median_time_ns,median_overhead_pct,ci_lower_pct,ci_upper_pct,overhead_pct`
   - Description: Median execution time, paired overhead relative to unchecked Mode U, and 95% bootstrap confidence intervals.

3. **Machine Environment Metadata**:
   - Path: `results/env_windows.json`
   - Records Windows OS version, CPU processor brand, MSYS2 GCC compiler version, and compilation flags.

---

## 5. Cross-Compilation Smoke Test Note

- In Linux/WSL2 host environments, the `x86_64-w64-mingw32-gcc` cross-compiler package was probed and verified as **not pre-installed**.
- Native Windows execution is therefore validated directly via MSYS2 UCRT64 GCC and PowerShell scripts.
