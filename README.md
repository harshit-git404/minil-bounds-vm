# MiniL Bounds VM: Dispatch-Aware Bounds Checking Evaluation

This repository implements **MiniL** (a statically typed, procedural language with arrays, functions, and recursion), an optimizing bytecode compiler (Python 3 stdlib), and an efficient stack-based virtual machine (C11, GCC `-O2`), designed to evaluate bounds-checking overheads, static elimination, loop hoisting, instruction fusion, and dispatch-vs-comparison decomposition.

All results are fully reproducible from source. Every measured number is generated programmatically into `results/` without manual edits or artificial tuning.

---

## 1. Prerequisites

- **Operating System**: Linux (x86_64), WSL2, or MSYS2 on Windows
- **C Compiler**: GCC 11+ supporting C11 and GNU C computed `goto` extensions (`gcc -O2 -std=c11`)
- **Python**: Python 3.10+ (standard library only for compiler, sema, and harness; `matplotlib` and `numpy` for figure generation)
- **Utilities**: `make`, `taskset` (for core pinning)

---

## 2. Quick Start: Reproducing Everything from a Clean Clone

```bash
# 1. Clone repository and checkout branch
git checkout exp/build-baseline

# 2. Build all virtual machine variants and record system environment
make all

# 3. Run complete test suite (unit, integration, soundness, hoisting edge cases)
make test

# 4. Run main benchmark timing and counting experiments (25 rounds, pinned core)
make experiments

# 5. Run dispatch-vs-comparison decomposition and dispatch ablation study
make decomp_experiments

# 6. Run hardware performance counter probe and userspace RDTSC cycle analysis
python3 scripts/run_hardware_counters.py

# 7. Run mutation fault injection study and differential testing
python3 scripts/run_fault_injection.py

# 8. Generate all LaTeX tables and publication vector PDF figures
make tables
make figures
```

---

## 3. Project Structure

```
minil-bounds-vm/
├── benchmarks/              # 23 MiniL benchmarks (13 original + 10 extended)
├── compiler/                # Python stdlib compiler pipeline
│   ├── lexer.py             # Lexer / tokenizer
│   ├── parser.py            # Recursive descent parser
│   ├── ast_nodes.py         # Abstract syntax tree definitions
│   ├── sema.py              # Semantic analysis, type checking, scoping
│   ├── analysis.py          # Abstract interpretation interval domain (Mode S)
│   ├── hoisting.py          # ISA-preserving loop guard hoisting (Mode H)
│   ├── codegen.py           # Stack bytecode emitter for all modes
│   └── main.py              # Compiler driver CLI
├── vm/                      # Stack Virtual Machine in C11
│   ├── vm.h                 # Bytecode format, ISA opcodes, stack limits
│   └── vm.c                 # Interpreter supporting GOTO, SWITCH, DIRECT dispatch
├── scripts/                 # Reproducibility & measurement scripts
│   ├── collect_env.py       # Hardware, kernel, compiler environment collector
│   ├── run_timing_harness.py# 25-round paired timing harness & static/dynamic counts
│   ├── run_decomposition.py # Dispatch vs comparison decomposition & dispatch ablation
│   ├── run_hardware_counters.py # WSL2 PMU status & userspace RDTSC cycles
│   ├── run_fault_injection.py  # 7-operator fault injection & differential testing
│   ├── generate_tables.py   # LaTeX booktabs table generator
│   ├── generate_figures.py  # Vector PDF chart generator (matplotlib)
│   ├── build_windows.sh     # MSYS2 UCRT64 GCC Windows build script
│   ├── run_windows.ps1      # Windows PowerShell timing harness
│   └── run_windows.sh       # Windows MSYS2 Bash timing harness
├── tests/                   # Test suite (29 tests)
│   ├── test_lexer.py
│   ├── test_parser.py
│   ├── test_sema.py
│   ├── test_codegen.py
│   ├── test_analysis.py
│   ├── test_hoisting.py
│   ├── test_soundness.py    # Randomized abstract interpretation soundness
│   ├── test_vm.py           # In-bounds equivalence & out-of-bounds trap tests
│   └── run_tests.py         # Test runner driver
├── results/                 # Raw and summary CSV/JSON artifacts, LaTeX tables, figures
│   ├── env.json             # Pinned CPU, OS kernel, compiler flags, git hash
│   ├── timing_summary.csv   # Per-benchmark overheads with 95% bootstrap CIs
│   ├── static_counts.csv    # Static site elimination classification
│   ├── dynamic_counts.csv   # Dynamic instruction and check counts
│   ├── decomposition_summary.csv # Pure dispatch vs comparison share
│   ├── dispatch_ablation_summary.csv # GOTO vs SWITCH vs DIRECT vs OPT3
│   ├── rdtsc_summary.csv    # Userspace RDTSC cycle overheads
│   ├── fault_injection_summary.json # Mutation fault detection statistics
│   ├── tables/              # Generated LaTeX tables (*.tex)
│   └── figures/             # Generated publication figures (*.pdf)
├── docs/                    # Design documentation & decision log
│   ├── grammar.md           # Formal language grammar
│   ├── isa.md               # VM instruction set architecture specification
│   └── decisions.md         # Architecture and engineering decision log
├── REPORT.md                # Comprehensive final experiment report
└── Makefile                 # Build and automation recipes
```

---

## 4. Compilation Modes

- **Mode U (Unchecked)**: Baseline execution with no bounds checks (`OP_ALOAD`, `OP_ASTORE`).
- **Mode R (Redundant / Separate)**: Standard checked execution; emits explicit `OP_CHK` before every array access.
- **Mode F (Fused Checks)**: Replaces separate `OP_CHK` + `OP_ALOAD`/`OP_ASTORE` with fused checking opcodes (`OP_ALOADC`, `OP_ASTOREC`).
- **Mode S (Static Elimination)**: Uses abstract interpretation over the non-relational interval domain `[-inf, +inf]` with Kleene iteration, widening, and narrowing to prove access sites in-bounds. Mode S emits checks only at unproven sites.
- **Mode H (Loop Guard Hoisting)**: Hoists bounds checks out of innermost affine loops (`while (i < E) { ... i = i + c }`) by emitting a runtime pre-loop guard (`i+K >= 0 && E+d+K <= |a|`). Uses ordinary instructions without changing the VM ISA. Guard true branch jumps to a check-free fast loop copy; false branch executes the checked fallback loop.
- **Mode FS (Fused Static)**: Fused checks (`OP_ALOADC`/`OP_ASTOREC`) only at sites not proven safe by interval analysis.
- **Mode FH (Fused Hoisting)**: FS combined with loop guard hoisting (guarded sites execute plain access in fast loop, fused in fallback loop).
- **Mode N (Decomposition Dispatch)**: Experimental mode emitting `OP_NOPCHK` before access (extra dispatch, zero comparison).
- **Mode FN (Decomposition Fused No-Check)**: Experimental opcode-fusion without comparison (`OP_ALOADN`/`OP_ASTOREN`).

---

## 5. Windows Cross-Validation Build (MSYS2 UCRT64)

To build and run on Windows under MSYS2 UCRT64 GCC:
```bash
# In MSYS2 UCRT64 shell:
bash scripts/build_windows.sh
bash scripts/run_windows.sh

# Or from PowerShell on Windows:
powershell -ExecutionPolicy Bypass -File scripts/run_windows.ps1
```