# Architectural and Engineering Decisions Log

This document records architectural, design, and engineering decisions made during the implementation and evaluation of `minil-bounds-vm`.

---

## Decision 1: Tracking Canonical Bounds Trap Sites
- **Context**: When code transformations like loop-guard hoisting duplicate loops, PC addresses of array accesses can change between baseline (R) and transformed (H) modes.
- **Decision**: In addition to opcode-level reporting, every array access site in MiniL source retains a compile-time static `site_id`. Bounds check errors report PC, array name, and `site_id` (encoded in instruction operand `b` where unused, or mapped via symbol table). This ensures canonical comparison across modes during differential testing.

## Decision 2: Static Analysis Interval Domain Assumptions
- **Context**: Standard interval abstract interpretation assumes ideal integers or explicit bit-width wrapping.
- **Decision**: MiniL assumes no 64-bit integer wraparound in program index expressions, consistent with Section III-D and VI of the paper design. The interval domain uses `[-inf, +inf]` over mathematical integers, truncating integer division, and C99 remainder bounds `x % N in [-(|N|-1), |N|-1]`.

## Decision 3: Direct-Threaded Dispatch Architecture
- **Context**: Task 7 requested direct-threaded dispatch (pre-resolved handler addresses in the instruction stream).
- **Decision**: Implemented direct-threaded dispatch by translating bytecode opcodes into an array of function label pointers (`direct_table`) at program load time. The interpreter loop dispatches via `goto *direct_table[pc]`, completely eliminating table indexing during execution.

## Decision 4: Isolation of Experimental Decomposition Opcodes
- **Context**: Task 6 requires experimental opcodes (`NOPCHK`, `ALOADN`, `ASTOREN`) to isolate bytecode dispatch overhead from check comparison costs.
- **Decision**: The trusted ISA claim for modes S, H, FS, FH relies solely on the 32 standard opcodes. The experimental decomposition opcodes are compiled only under `#ifdef EXPERIMENTAL_DECOMP` in distinct build targets (`minil-vm-decomp-*`), preserving the integrity of the trusted ISA claim.

## Decision 5: WSL2 Hardware Counter Fallback to Userspace RDTSC
- **Context**: Task 8 requested PMU hardware event counters via `perf stat`. The WSL2 virtualized Microsoft kernel lacks `linux-tools` perf support and PMU access.
- **Decision**: Adhering strictly to the paper's honesty rules, we documented the PMU unavailability in `results/hardware_counters_status.json` and implemented an exact userspace `__rdtsc()` timestamp counter mechanism in the VM (`RDTSC_CYCLES`), providing cycle counts without kernel intervention.

## Decision 6: Sizing Extended Benchmarks for Timing Stability
- **Context**: Task 4 and Task 9 specify that benchmarks should run in ~30-100 ms in mode U.
- **Decision**: Tuned problem parameters (e.g., GEMM $N=80$, Jacobi-1D timesteps=10, LCS length=700) so that all 23 benchmarks execute in the 30-100 ms window on modern x86_64 architectures, minimizing timer quantization error while avoiding long-running harness timeouts.

## Decision 7: Canonical Timing and Decomposition Benchmark Sets and Consistency
- **Context**: Mode R overhead is reported as +2.16% in the full timing evaluation and +2.91% in the decomposition/dispatch-ablation evaluation.
- **Decision**: The canonical timing run (`results/timing_summary.csv`, `results/aggregate_summary.json`, `results/timing_raw_1792835669.csv`) evaluates all 22 array benchmarks (+ fib null control) over 25 measurement rounds on a pinned core. On this combined suite, Mode R geometric mean overhead is +2.16%. Evaluated strictly on the original 12 array benchmarks, the timing run measures Mode R overhead as +2.89%. The decomposition and dispatch-ablation run (`results/dispatch_ablation_summary.csv`, `results/decomposition_summary.csv`, `results/decomposition_raw.csv`) evaluates 4 dispatch architectures across 9 modes over 15 measurement rounds on the 12 original array benchmarks, measuring Mode R overhead as +2.91%. On the identical 12-benchmark set, the two independent runs are virtually identical (+2.89% vs +2.91%, within 0.02 percentage points). The difference between +2.16% and +2.91% is solely the suite size (22 benchmarks vs 12 benchmarks). Both sets are maintained canonically and tracked in `results/paper_numbers.json`.
