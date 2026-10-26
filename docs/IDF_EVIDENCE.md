# MiniL Bounds-Checking Hoisting: IDF Evidence Pack

This document constitutes the evidence pack for the MiniL bounds-checking optimization and loop-guard hoisting pass on branch `exp/build-baseline`. All formulas, eligibility rules, bytecode sequences, counts, and statistical confidence intervals are drawn directly from active source code, benchmark suites, and measured CSV/JSON artifacts.

---

## 1. Description of the Hoisting Transformation

Loop-guard hoisting (Mode H) is an ahead-of-time loop-versioning optimization that eliminates redundant dynamic array bounds checks from innermost loops without modifying the virtual machine interpreter or adding instruction set extensions. When an innermost `while` loop iterates monotonically through an affine index range ($i + K$) bounded by an invariant limit expression ($E$), the compiler synthesizes a pre-loop conditional guard ($i + K \ge 0 \land E + d + K \le |A|$) evaluated once prior to loop entry. If the guard evaluates to true, control transfers to an optimized "fast" loop clone where all eligible `CHK` instructions are omitted, allowing memory loads (`ALOAD`) and stores (`ASTORE`) to proceed unconditionally at full interpreter speed. If the guard evaluates to false, control branches directly to a safe "slow" loop clone retaining identical individual `CHK` instructions that trap with exact source site provenance upon an out-of-bounds access. Both clones converge at a single join point following loop exit, preserving strict program semantics, termination behavior, and exception fidelity across all input states.

---

## 2. Eligibility & Refusal Conditions (compiler/hoisting.py)

The eligibility checks are implemented in `HoistingPlanner._is_eligible_loop()` and `HoistingPlanner._extract_index_form()` in `compiler/hoisting.py`.

### Eligibility Conditions (Must All Hold)
1. **Loop Structure**: The loop must be an innermost `WhileStmt`. If any statement in the body contains another `WhileStmt`, the loop is rejected (`has_nested_while`).
2. **Canonical Condition Shape**: The loop condition must be a binary comparison of the form `i < E` or `i <= E`, where `i` is a simple local variable (`VarExpr`) and `E` is an arbitrary side-effect-free expression.
3. **Purity of Bound Expression ($E$)**: Expression $E$ must contain no function calls (`CallExpr`), ensuring evaluation cannot mutate program state or trigger side effects.
4. **Loop-Invariance of Bound Expression ($E$)**: None of the variables referenced in $E$ may be assigned anywhere within the loop body (`assigned_vars & bound_vars == set()`).
5. **Single Loop-Index Assignment**: The loop index variable `i` must be assigned exactly once within the entire loop body (`assign_count == 1`).
6. **Last-Statement Increment**: The single assignment to `i` must be the absolute final statement of the loop body (`body[-1]`).
7. **Canonical Monotonic Increment**: The increment statement must match `i = i + c` or `i = c + i`, where `c` is an integer literal constant (`IntLiteral`) satisfying $c \ge 1$.
8. **Candidate Array Access Sites**: Every hoisted array access must reference a known fixed-size array $A$ and have an index expression conforming to:
   - `i` (stride 1, offset 0),
   - `i + K` (positive affine offset), or
   - `i - K` (negative affine offset),
   where $K$ is a side-effect-free expression whose free variables are strictly invariant (unassigned) across the loop body.

### Refusal Conditions (Pass Refuses to Transform)
The pass aborts hoisting on any loop exhibiting:
- **Non-innermost loops**: Outer loops enclosing nested `while` statements.
- **Descending loops**: Loops stepping downward (`i > E`, `i >= E`, or $i = i - c$).
- **Non-constant or dynamic step**: Increments using variables or complex terms (`i = i + step` or `i = i * 2`).
- **Zero or negative step**: Increment step $c \le 0$.
- **Multiple assignments to loop variable**: Any conditional or secondary update to `i` within the body (e.g., `if (...) i = i + 1`).
- **Non-terminal updates**: Any loop where the increment of `i` occurs before the final statement.
- **Variant limit expressions**: Any mutation to a variable appearing in bound expression $E$ inside the loop.
- **Non-affine / Data-dependent indexing**: Indirect or non-linear index expressions, including table lookups ($A[B[i]]$), scaled indices ($A[i \times 2]$), or indices depending on loop-variant variables ($A[i + temp]$ where $temp$ is modified).

### Deviations from Paper Description
- **Affine Offsets**: The paper's conceptual presentation highlights canonical unit-stride loops (`A[i]`). The actual implementation in `compiler/hoisting.py` fully handles general invariant affine offsets (`A[i + K]` and `A[i - K]`).
- **Compound Guards**: The implementation synthesizes multi-site compound conjunctions: if a loop accesses $A[i]$, $A[i+1]$, and $B[i]$, a single hoisted guard checks lower and upper bounds across all candidate access sites simultaneously. If any site fails the invariance test, only the unproven sites retain checks or the loop is kept unversioned.

---

## 3. Guard Formula & Pass Pseudocode

### Guard Formula as Implemented
For each eligible array access site on array $A$ (with declared length $|A|$) indexed by $i + K_{\text{eff}}$ in a loop with condition $i < E$ (or $i \le E$):
$$\text{Lower Guard: } (i + K_{\text{eff}} \ge 0)$$
$$\text{Upper Guard: } (E + d + K_{\text{eff}} \le |A|)$$
where offset constant $d = 1$ if the condition operator is `<=`, and $d = 0$ if `<`. For a simple index $A[i]$, $K_{\text{eff}} = 0$.
The complete hoisted guard is the conjunction of all lower and upper guards across all candidate sites:
$$\text{Guard} = \bigwedge_{\text{site } s} \left( (i_0 + K_{\text{eff}}^{(s)} \ge 0) \land (E + d + K_{\text{eff}}^{(s)} \le |A_s|) \right)$$

### Pass Pseudocode (compiler/hoisting.py, <= 40 lines)
```python
def hoist_loop(while_stmt, sema, safe_sites):
    if not is_innermost_while(while_stmt): return while_stmt
    i_var, bound_expr, op = parse_condition(while_stmt.cond) # i < E or i <= E
    if not is_side_effect_free_and_invariant(bound_expr, while_stmt.body): return while_stmt
    if not is_last_stmt_canonical_increment(while_stmt.body, i_var): return while_stmt
    
    candidate_sites, guard_conjuncts = [], []
    for access in find_array_accesses(while_stmt.body):
        if access.site_id in safe_sites: continue
        k_expr = extract_affine_offset(access.index, i_var)
        if k_expr is None or not is_invariant(k_expr, while_stmt.body): return while_stmt
        arr_len = sema.lookup_array(access.array_name).length
        d = 1 if op == "<=" else 0
        guard_conjuncts.append(BinOp(">=", Add(Var(i_var), k_expr), IntLiteral(0)))
        guard_conjuncts.append(BinOp("<=", Add(Add(bound_expr, IntLiteral(d)), k_expr), IntLiteral(arr_len)))
        candidate_sites.append(access.site_id)
        
    if not candidate_sites: return while_stmt
    fast_body = clone_ast(while_stmt.body)
    fast_safe_sites = safe_sites | set(candidate_sites)
    fast_loop = WhileStmt(while_stmt.cond, fast_body)
    slow_loop = clone_ast(while_stmt) # preserves original CHK sites
    compound_guard = combine_with_and(guard_conjuncts)
    return IfStmt(compound_guard, then_block=[fast_loop], else_block=[slow_loop])
```

---

## 4. Worked Example: examples/demo_sum.minil

### Source Code (`examples/demo_sum.minil`)
```c
int A[10];

int sum_slice(int m) {
    int i = 0;
    int s = 0;
    while (i < m) {
        s = s + A[i];
        i = i + 1;
    }
    return s;
}

int main() {
    int i = 0;
    while (i < 10) {
        A[i] = i * 10;
        i = i + 1;
    }
    int total = sum_slice(10);
    print(total);
    return 0;
}
```

### Side-by-Side Disassembly of `sum_slice` (Mode R vs Mode H)

```
MODE R (Standard Separate Check)          MODE H (Loop-Guard Hoisting)
----------------------------------------  ----------------------------------------------------
0002: ENTER    2                          0002: ENTER    2
0003: PUSH     0                          0003: PUSH     0
0004: STORE    1          ; i = 0         0004: STORE    1          ; i = 0
0005: PUSH     0                          0005: PUSH     0
0006: STORE    2          ; s = 0         0006: STORE    2          ; s = 0
                                          ; --- HOISTED GUARD EVALUATION ---
                                          0007: LOAD     1          ; load i
                                          0008: PUSH     0
                                          0009: GE                  ; i >= 0
                                          0010: JZ       -> pc 17   ; short-circuit to false
                                          0011: LOAD     0          ; load m
                                          0012: PUSH     10         ; length(A)
                                          0013: LE                  ; m <= 10
                                          0014: JZ       -> pc 17
                                          0015: PUSH     1          ; guard true
                                          0016: JMP      -> pc 18
                                          0017: PUSH     0          ; guard false
                                          0018: JZ       -> pc 34   ; IF FALSE -> GOTO SLOW LOOP
; --- CHECKED LOOP ---                    ; --- FAST LOOP (NO CHECKS) ---
0007: LOAD     1          ; loop head     0019: LOAD     1          ; loop head
0008: LOAD     0                          0020: LOAD     0
0009: LT                                  0021: LT
0010: JZ       -> pc 22   ; exit loop     0022: JZ       -> pc 33   ; exit fast loop
0011: LOAD     2                          0023: LOAD     2
0012: LOAD     1                          0024: LOAD     1
0013: CHK      A (id=0)   ; RUNTIME CHK   [CHK ELIMINATED BY HOISTING]
0014: ALOAD    A (id=0)                   0025: ALOAD    A (id=0)   ; UNCHECKED LOAD
0015: ADD                                 0026: ADD
0016: STORE    2                          0027: STORE    2
0017: LOAD     1                          0028: LOAD     1
0018: PUSH     1                          0029: PUSH     1
0019: ADD                                 0030: ADD
0020: STORE    1                          0031: STORE    1
0021: JMP      -> pc 7                    0032: JMP      -> pc 19   ; fast loop back-edge
                                          0033: JMP      -> pc 49   ; goto continuation
                                          ; --- SLOW LOOP (CHECKED FALLBACK) ---
                                          0034: LOAD     1          ; slow loop head
                                          0035: LOAD     0
                                          0036: LT
                                          0037: JZ       -> pc 49   ; exit slow loop
                                          0038: LOAD     2
                                          0039: LOAD     1
                                          0040: CHK      A (id=0)   ; ORIGINAL RUNTIME CHK
                                          0041: ALOAD    A (id=0)
                                          0042: ADD
                                          0043: STORE    2
                                          0044: LOAD     1
                                          0045: PUSH     1
                                          0046: ADD
                                          0047: STORE    1
                                          0048: JMP      -> pc 34   ; slow loop back-edge
; --- CONTINUATION ---                    ; --- CONTINUATION ---
0022: LOAD     2                          0049: LOAD     2
0023: RET                                 0050: RET
```

---

## 5. Failing-Guard Behavior & Exact Provenance Preservation

When `sum_slice` is called with $m = 15$ on array $A[10]$, the hoisted guard expression $15 \le 10$ evaluates to false. Execution branches to the slow loop clone at pc 0034. On iteration $i = 10$, instruction `CHK A (id=0)` triggers.

### Execution Output
- **Mode R**:
  ```text
  TRAP: bounds check failed for array 'A' at pc 13, site 0 (index 10, size 10)
  (exit code: 2)
  ```
- **Mode H**:
  ```text
  TRAP: bounds check failed for array 'A' at pc 40, site 0 (index 10, size 10)
  (exit code: 2)
  ```

### Provenance Invariant
Both modes abort with exit code `2`, identifying the exact same failing array `A`, identical illegal index `10`, identical allocated size `10`, and identical static source site identifier (`site 0`). The only difference is the physical instruction stream offset (pc 13 vs pc 40), verifying 100% exception equivalence.

---

## 6. ISA-Preserving Evidence

### Automated Verification Script (`scripts/verify_isa_preserving.py`)
Verification was executed on all 24 benchmark and example programs across 6 compilation modes (U, R, S, H, FS, FH) for 144 independent bytecode inspection configurations.
- **Base Trusted ISA**: Defined by `vm/vm.h` without `-DEXPERIMENTAL_DECOMP`. Exactly 32 opcodes (opcodes 0..31: `NOP` through `ASTOREC`).
- **Mode H Opcode Conformance**: In all 24 programs, Mode H emitted strictly standard base opcodes (`PUSH`, `LOAD`, `STORE`, `LE`, `GE`, `LT`, `GT`, `JZ`, `JNZ`, `JMP`, `ALOAD`, `ASTORE`, `CHK`).
- **No Experimental Opcodes**: Opcodes 32, 33, and 34 (`NOPCHK`, `ALOADN`, `ASTOREN`) are never emitted in Mode H.
- **VM Source Independence**: Grepping `vm/vm.c` and `vm/vm.h` for `mode`, `hoist`, or optimization flags returns 0 matches. The virtual machine has zero code paths aware of Mode H.

### VM Trusted Opcode Table (Base Build)
| Opcode ID | Mnemonic | Operands | Description |
|:---|:---|:---|:---|
| 0 | `OP_NOP` | none | No operation |
| 1 | `OP_PUSH` | imm | Push immediate 64-bit integer |
| 2 | `OP_POP` | none | Pop and discard top of stack |
| 3 | `OP_DUP` | none | Duplicate top stack item |
| 4 | `OP_LOAD` | slot | Load local variable from frame slot |
| 5 | `OP_STORE` | slot | Store top of stack into frame slot |
| 6 | `OP_ADD` | none | Binary addition |
| 7 | `OP_SUB` | none | Binary subtraction |
| 8 | `OP_MUL` | none | Binary multiplication |
| 9 | `OP_DIV` | none | Binary integer division (traps on 0) |
| 10 | `OP_MOD` | none | Binary modulo (traps on 0) |
| 11 | `OP_NEG` | none | Arithmetic negation |
| 12 | `OP_EQ` | none | Equality comparison |
| 13 | `OP_NE` | none | Inequality comparison |
| 14 | `OP_LT` | none | Less-than comparison |
| 15 | `OP_LE` | none | Less-than-or-equal comparison |
| 16 | `OP_GT` | none | Greater-than comparison |
| 17 | `OP_GE` | none | Greater-than-or-equal comparison |
| 18 | `OP_NOT` | none | Logical negation |
| 19 | `OP_JMP` | target_pc | Unconditional jump |
| 20 | `OP_JZ` | target_pc | Jump if top of stack is zero |
| 21 | `OP_JNZ` | target_pc | Jump if top of stack is non-zero |
| 22 | `OP_CALL` | target_pc, nargs | Call function |
| 23 | `OP_ENTER` | nlocals | Allocate stack frame |
| 24 | `OP_RET` | none | Return from function |
| 25 | `OP_PRINT` | none | Print integer to stdout |
| 26 | `OP_HALT` | none | Terminate VM execution |
| 27 | `OP_ALOAD` | array_id | Array load: index on stack |
| 28 | `OP_ASTORE` | array_id | Array store: value, index on stack |
| 29 | `OP_CHK` | array_id | Bounds check: index on stack (traps if out of bounds) |
| 30 | `OP_ALOADC` | array_id | Fused check + load |
| 31 | `OP_ASTOREC` | array_id | Fused check + store |

**Task 1 Pass Line**:
`PASS: ISA-preserving claim verified across 24 benchmarks and 6 modes (144 total checks). All emitted opcodes belong to the base trusted ISA (0..31); Mode H introduces zero new opcodes; vm/vm.c and vm/vm.h contain zero mode-specific code paths.`

---

## 7. Measured Experimental Results

All numbers below are extracted from canonical result files (`results/timing_raw_1792835669.csv`, `results/static_counts.csv`, `results/dynamic_counts.csv`, `results/significance.csv`, `results/fault_injection_results.csv`, `results/bytecode_size_summary.csv`).

### Dynamic Checks Executed (R vs S vs H)
- **Mode R (Separate Checks)**: 34,955,868 checks executed across the 22-benchmark suite.
- **Mode S (Interval Analysis)**: 10,063,184 checks executed (71.2% eliminated vs R).
- **Mode H (Hoisting)**: 4,733,620 checks executed (86.5% eliminated vs R; 30,222,248 checks removed).
- *Source*: `results/dynamic_counts.csv`

### Static Site Classification (22 Benchmarks, 58 Sites)
- **Total Static Array Access Sites**: 58
- **Proved Safe by Interval Analysis (Mode S)**: 25 sites (43.1%)
- **Versioned & Guarded by Hoisting (Mode H)**: 23 sites (39.7%)
- **Residual Checks Retained in Mode H**: 10 sites (17.2%)
- **Combined Statically Handled in Mode H**: 48 / 58 sites (82.8%)
- *Source*: `results/static_counts.csv`

### Execution Time Overheads vs Mode U (Geometric Mean & 95% Bootstrap CIs)
*Source*: `results/significance.csv` (Canonical run: Computed GOTO, GCC -O2, core pinned, governor performance)

| Suite | Mode | Geomean Overhead vs U | 95% Bootstrap CI | Significant vs U? | Sig. Benches |
|:---|:---|:---:|:---:|:---:|:---:|
| **Combined 22** | **R** | +2.16% | [+1.35%, +3.47%] | **YES** | 4 / 22 |
| Combined 22 | **F** | +3.49% | [+2.33%, +4.88%] | **YES** | 7 / 22 |
| Combined 22 | **S** | +1.10% | [-0.16%, +2.21%] | NO | 2 / 22 |
| **Combined 22** | **H** | **+0.69%** | **[-0.66%, +1.97%]** | **NO** | 2 / 22 |
| Combined 22 | **FS** | +1.80% | [+0.29%, +3.12%] | **YES** | 4 / 22 |
| Combined 22 | **FH** | +1.24% | [+0.14%, +2.50%] | **YES** | 2 / 22 |
| **Original 12** | **R** | +2.89% | [+1.60%, +4.31%] | **YES** | 2 / 12 |
| Original 12 | **F** | +3.65% | [+2.37%, +5.72%] | **YES** | 4 / 12 |
| Original 12 | **S** | +1.91% | [+0.04%, +3.75%] | **YES** | 2 / 12 |
| **Original 12** | **H** | **+0.58%** | **[-1.22%, +2.58%]** | **NO** | 2 / 12 |
| Original 12 | **FS** | +2.41% | [+0.50%, +4.16%] | **YES** | 3 / 12 |
| Original 12 | **FH** | +1.81% | [-0.05%, +2.98%] | NO | 1 / 12 |

### Paired Confidence Intervals (Mode H vs R and Mode S vs R)
*Source*: `results/significance.csv`

| Suite | Comparison | Geomean Overhead Ratio | 95% Bootstrap CI | Excludes 0%? | Statistically Sig? |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Combined 22** | **H vs R** | **-1.86%** | **[-2.87%, -0.18%]** | **YES** | **YES** (faster than R) |
| **Combined 22** | **S vs R** | **-1.44%** | **[-3.18%, -0.08%]** | **YES** | **YES** (faster than R) |
| Original 12 | H vs R | -1.84% | [-3.50%, +0.61%] | NO | NO (overlaps 0) |
| Original 12 | S vs R | -0.87% | [-3.09%, +1.24%] | NO | NO (overlaps 0) |

### Bytecode Size Growth
*Source*: `results/bytecode_size_summary.csv`
- **Mode R**: +6.1% vs Mode U (geometric mean)
- **Mode F**: +0.0% vs Mode U (fused superinstructions replace load/stores 1-to-1)
- **Mode S**: +1.1% vs Mode U (safe checks omitted)
- **Mode H**: +10.2% vs Mode U (loop body duplication + guard prelude)
- **Mode FS**: +0.0% vs Mode U
- **Mode FH**: +9.2% vs Mode U

### Fault Injection & Safety Verification Totals
*Source*: `results/fault_injection_results.csv`, `results/fault_injection_summary.json`
- **Total Mutants Tested**: 329 across 8 mutation operators.
- **Faulty Mutants (Dynamic Bounds Violation)**: 213 mutants trapped by Mode R.
- **Benign Mutants (In-Bounds Semantics)**: 116 mutants executed in-bounds with 0 bounds traps.
- **Definite Compile-Time Violations**: 5 mutants flagged at compile time (100% precision, 0 false alarms).
- **Static Detection of Faulty Mutants**: 195 / 213 faulty mutants noticed statically (91.5% detection rate).
- **Mode U Silent Corruptions**: 181 / 213 (85.0% silent corruption rate without checks).
- **Mode U Process Crashes (SIGSEGV/Abort)**: 0 / 213 (0.0% crash visibility in unchecked execution).
- **Differential Testing Divergences**: 0 divergences across all modes (R, F, S, H, FS, FH produce identical outputs and identical trap sites).
- **False Alarms on Benign Mutants**:
  - *Definition of Benign Mutant*: A mutant program whose runtime memory accesses strictly remain within allocated array bounds when verified dynamically under Mode R.
  - *Measured Definite Violations on Benign Mutants*: **0 / 116 (0.0%)**
  - *Measured Static Alarms on Benign Mutants*: **0 / 116 (0.0%)**
  - *False-Alarm Rate*: **0.0%** (interval analysis conservatively handles loop modifications without generating spurious alarms on valid in-bounds variations).

---

## 8. Honest Limitations

1. **Non-Innermost Loops**: Outer loops enclosing nested `while` statements are not versioned or hoisted. In multidimensional matrix operations (e.g. `matmul`), inner loop checks are eliminated, but outer loop index accesses are not hoisted.
2. **Descending Loops Unhandled**: Loops iterating downward (`while (i > 0) { i = i - 1; }`) are refused by the pass.
3. **Non-Constant / Dynamic Stride**: Strided loops with non-constant increments (`i = i + step` where `step` is a variable) or non-linear updates (`i = i * 2`) are refused.
4. **Modified Bound Expressions**: If any variable within limit expression $E$ is reassigned within the loop body, hoisting is aborted to prevent stale bound guards.
5. **Integer Wraparound Assumption**: MiniL operates on 64-bit signed integers. The guard generation assumes $E + K$ does not exceed $2^{63}-1$. In adversarial arithmetic with near-$\text{INT64\_MAX}$ bounds, integer overflow could theoretically cause guard evaluation anomalies.
6. **Code Size Expansion**: Loop versioning duplicates loop bodies, yielding a +10.2% geometric mean bytecode size growth (+48.6% worst-case in `sieve`).
7. **Single Machine Architecture**: All reported microbenchmarks were evaluated on a single testbed (Intel Core i7-10700K @ 3.80GHz, Ubuntu 24.04 LTS, Linux 6.8.0-90-generic, GCC 13.3.0). Relative cache and branch predictor behavior may vary on ARM, RISC-V, or out-of-order architectures with differing dispatch costs.
8. **Measurement Noise Floor**: In an interpreter where bounds check overhead in Mode R is +2.16%, individual benchmark overheads range within $[-2.75\%, +10.33\%]$. Paired bootstrap confidence intervals are essential to distinguish true optimization signal from dispatch and host system noise.

---

## 9. Classical Techniques / What is Not Claimed

To maintain scientific integrity and avoid overclaiming, we clarify standard techniques utilized in this system that are classical prior art:
1. **Interval Analysis (Abstract Interpretation)**: The interval domain $[l, u]$ with widening/narrowing and transfer functions for arithmetic and comparisons follows classical abstract interpretation (Cousot & Cousot, 1977). We make no claim to novelty in interval arithmetic.
2. **Loop Versioning**: Splitting a loop into an unchecked fast clone and a checked slow fallback guarded by a pre-loop condition is a classical compiler optimization dating back to Fortran vectorizing compilers and modern JITs (HotSpot, V8).
3. **Superinstructions / Instruction Fusion**: Fusing separate check and load instructions (`CHK` + `ALOAD` $\to$ `ALOADC`) is a well-established technique in virtual machine interpreters (Bell 1973; Proebsting 1995; Gagnon & Hendren 2003).

### What IS Claimed (The Paper's Novel Contribution)
- An empirical demonstration that loop-guard hoisting achieves **86.5% check elimination** and reduces bounds-checking overhead to **+0.69%** (statistically indistinguishable from unchecked execution) while remaining **100% ISA-preserving** (requiring zero interpreter bytecode extensions, zero opcode modifications, and zero changes to the underlying C virtual machine).
- A rigorous decomposition showing that in modern interpreters, up to **46.5% - 59.5%** of separate bounds check overhead stems from dispatch instruction dispatching rather than comparison arithmetic itself.

---

## 10. Figure Inventory (paper/figures/)

| Filename | Type | Description | Source Data File |
|:---|:---:|:---|:---|
| `architecture.pdf` / `.png` | Diagram | Architectural pipeline diagram showing source compilation through lexer, parser, sema, interval analysis, hoisting planner, codegen, bytecode, and VM dispatchers. | N/A (vector diagram in `scripts/generate_figures.py`) |
| `decomposition.pdf` / `.png` | Bar Chart | Decomposition of separate check overhead into dispatch (Mode N) vs comparison vs fusion (Mode F / FN) across benchmarks under Computed GOTO. | `results/decomposition_summary.csv` |
| `dispatch_ablation.pdf` / `.png` | Bar Chart | Geometric mean bounds checking overhead across four interpreter dispatch architectures (Computed GOTO, Switch-in-a-loop, Direct-Threaded, and GOTO -O3). | `results/dispatch_ablation_summary.csv` |
| `dispatch_share.pdf` / `.png` | Bar Chart | Share of separate check cost ($R$) explained strictly by dispatch overhead ($N$), with 95% bootstrap confidence intervals for each dispatch architecture. | `results/paper_numbers.json` |
| `dynamic_checks.pdf` / `.png` | Bar Chart | Dynamic bounds checks executed per benchmark across optimization modes R, S, H, and FH on a log scale. | `results/dynamic_counts.csv` |
| `fault_injection_bars.pdf` / `.png` | Bar Chart | Fault injection counts by mutation operator, displaying faulty trapped mutants, benign mutants, definite compile-time violations, and new static alarms. | `results/fault_injection_results.csv` |
| `loop_versioning.pdf` / `.png` | Diagram | Control flow diagram of hoisted loop versioning: synthesized guard branching to unchecked fast loop copy vs checked slow loop fallback. | N/A (vector diagram in `scripts/generate_figures.py`) |
| `overhead_bars.pdf` / `.png` | Bar Chart | Per-benchmark execution time overhead relative to Mode U for modes R, F, S, H, FS, FH with 95% bootstrap error bars. | `results/timing_summary.csv` |
| `scatter_overhead_instructions.pdf` / `.png` | Scatter | Correlation between dynamic instruction count percentage increase vs execution time overhead percentage across all benchmark-mode configurations. | `results/timing_summary.csv`, `results/dynamic_counts.csv` |
| `static_classification.pdf` / `.png` | Stacked Bar | Static classification of 58 array access sites across 22 benchmarks: proved safe (S), versioned and hoisted (H), or residual runtime check. | `results/static_counts.csv` |

---

## 11. Screenshot Inventory (results/demo/)

| File | What It Demonstrates | Suggested Caption |
|:---|:---|:---|
| `results/demo/01_env.txt` | Clean testbed configuration: OS, CPU model, GCC version, Python runtime, and relative paths. | *Figure S1: Reproducible evaluation environment and toolchain specifications.* |
| `results/demo/02_make_test.txt` | Complete test suite execution passing 100% of unit tests, AST tests, parser tests, sema tests, analysis tests, and VM execution tests. | *Figure S2: Regression and verification test suite passing all test cases.* |
| `results/demo/03_sample_program.txt` | Source code of `examples/demo_sum.minil` with parameter-bounded loop iteration over array `A[10]`. | *Figure S3: Annotated MiniL source example for loop hoisting.* |
| `results/demo/04_disassembly.txt` | Side-by-side bytecode disassembly across modes U, R, F, S, and H showing guard generation and check elimination. | *Figure S4: Disassembly comparison showing hoisted guard and unchecked fast loop clone.* |
| `results/demo/05_run_modes.txt` | Execution of `demo_sum.minil` across all 7 compilation modes (U, R, F, S, H, FS, FH) producing identical output (`450`). | *Figure S5: Behavioral invariance and identical output across all compilation modes.* |
| `results/demo/06_out_of_bounds.txt` | Out-of-bounds error handling: Mode U silent memory corruption vs Mode R clean runtime abort and trap reporting. | *Figure S6: Memory safety violation: silent memory corruption in Mode U vs clean trap in Mode R.* |
| `results/demo/07_interval_analysis_report.txt` | Static interval analysis report showing proven safe sites and interval refinement on `benchmarks/bubble.minil`. | *Figure S7: Interval analysis diagnostic output proving access sites safe at compile time.* |
| `results/demo/08_hoisting_guard_fallback.txt` | Failing guard demonstration: Mode H takes slow fallback and traps with identical site ID (`site 0`) and array details as Mode R. | *Figure S8: Guard failure fallback preserving exact trap site provenance.* |
| `results/demo/09_mutant_example.txt` | Step-by-step trace of mutant detection: off-by-one operator mutation triggering compile-time static alarm and runtime trap. | *Figure S9: Off-by-one mutation detection: static alarm and runtime trap verification.* |
| `results/demo/10_timing_summary.txt` | Formatted table of benchmark execution times, overheads, and 95% bootstrap confidence intervals. | *Figure S10: Execution time overheads and 95% confidence intervals across benchmark suite.* |
| `results/demo/11_decomposition_summary.txt` | Overhead decomposition across Computed GOTO, Switch, Direct-Threaded, and -O3 dispatchers. | *Figure S11: Dispatch architecture ablation and check cost decomposition summary.* |
| `results/demo/12_fault_injection_summary.txt` | High-level fault injection summary metrics: 329 mutants, 91.5% static detection, 0 false alarms, 0 differential divergences. | *Figure S12: Comprehensive fault injection and mutation testing verification summary.* |
