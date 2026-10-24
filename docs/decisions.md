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
