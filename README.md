# MiniL Bounds VM: Dispatch-Aware Bounds Checking Evaluation

This repository implements **MiniL** (a statically typed, procedural language with arrays, functions, and recursion), an optimizing bytecode compiler (Python 3 stdlib), and an efficient stack-based virtual machine (C11, GCC `-O2`), designed to evaluate bounds-checking overheads, static elimination, loop hoisting, instruction fusion, and dispatch-vs-comparison decomposition.

All results are fully reproducible from source. Every measured number is generated programmatically into `results/` without manual edits or artificial tuning.

---

## 1. Prerequisites

- **Operating System**: Linux (x86_64), WSL2, or MSYS2 on Windows (see [`docs/WINDOWS.md`](docs/WINDOWS.md))
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

# 8. Generate all LaTeX tables, publication vector PDFs, and 300-dpi PNGs
make tables
make figures

# 9. Copy all publication-ready assets into paper/figures/ and paper/tables/
make paper-assets

# 10. Run canonical numbers export, paper consistency audit, and statistical significance tests
python3 scripts/export_paper_numbers.py
python3 scripts/check_paper_numbers.py
python3 scripts/compute_significance.py

# 11. Run machine-code handler analysis and layout sensitivity checks
python3 scripts/analyze_handlers.py

# 12. Run robustness repeat sessions
python3 scripts/run_robustness_repeats.py

# 13. Run interactive terminal demo script (<=100 cols, saves to results/demo/)
bash scripts/demo.sh
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
│   ├── codegen.py           # Multi-mode bytecode code generator
│   ├── opcodes.py           # Opcodes and metadata definitions
│   └── disasm.py            # Bytecode disassembler
├── docs/                    # Architectural decisions, ISA, grammar, and Windows guide
│   ├── decisions.md         # Record of all design and experimental decisions
│   ├── grammar.md           # Formal grammar specification
│   ├── isa.md               # Bytecode instruction set architecture
│   └── WINDOWS.md           # Native MSYS2 UCRT64 Windows instructions
├── examples/                # Example MiniL programs (demo_sum.minil)
├── paper/                   # Research paper draft and publication assets
│   ├── figures/             # Vector PDFs and 300-dpi PNG charts and diagrams
│   ├── tables/              # LaTeX booktabs tables (.tex snippets)
│   └── paper.tex            # Research paper manuscript
├── results/                 # Machine-generated CSV and JSON experiment artifacts
│   ├── demo/                # Text outputs from demo script sections (01-12)
│   ├── figures/             # Generated publication figures (.pdf and .png)
│   ├── tables/              # Generated LaTeX table snippets (.tex)
│   ├── paper_numbers.json   # Canonical numbers index for paper traceability
│   ├── paper_number_audit.csv # Audit of paper claims vs measured data
│   └── significance.csv     # Paired bootstrap statistical significance CIs
├── scripts/                 # Automated experiment and analysis scripts
├── tests/                   # Test suite (unit, integration, randomized soundness)
├── vm/                      # Stack virtual machine in C11
│   ├── vm.c                 # Interpreter implementation (GOTO, SWITCH, DIRECT)
│   └── vm.h                 # Instruction and VM definitions
├── FINAL_REPORT.md          # Comprehensive final research and audit deliverable
├── LICENSE                  # License placeholder
├── Makefile                 # Top-level build orchestration
└── README.md                # This file
```

---

## 4. Key Results Summary

- **Mode R Baseline Overhead**: **+2.16%** on 22 array benchmarks (**+2.89%** on original 12) under computed `goto`.
- **Fused Checks (Mode F)**: **+3.49%** under computed `goto` (slower than Mode R), but **-2.41%** under `switch` dispatch.
- **Dispatch Decomposition (Mode N)**: Bytecode dispatch alone accounts for **48.5%** of separate check cost under computed `goto` and **83.1%** under `switch` dispatch. Direct-threading reduces check overhead to **+0.32%**.
- **Static & Dynamic Check Elimination**: Interval analysis proves **77.9%** of sites safe (original 12) and **87.5%** safe (22 benchmarks); loop-guard hoisting eliminates **88.5%** of dynamic checks without modifying the trusted VM ISA.
- **Fault Injection**: Across 329 mutants (213 faulty), static analysis flagged **91.5%** of faulty mutants, while unchecked execution (Mode U) never crashed and silently corrupted memory on **85.0%** of faults.