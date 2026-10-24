# MiniL Virtual Machine Instruction Set Architecture (ISA)

This document describes the virtual machine instruction set architecture, machine model, execution loop, memory layout, and bytecode binary format.

---

## 1. Machine Model

The MiniL VM is a stack-based virtual machine operating on 64-bit signed words (`int64_t`).

### 1.1 Architectural State
1. **Program Counter (`pc`)**: Index of the currently executing instruction in the code array.
2. **Operand Stack (`stack`)**: Flat array of 64-bit integer values evaluated during expression execution. Managed with stack pointer `sp` (points to the next free slot).
3. **Call Stack (`call_stack`)**: Stack of activation frames for function calls. Each frame stores:
   - `ret_pc`: Return instruction address.
   - `prev_bp`: Caller's base pointer in the operand stack.
4. **Base Pointer (`bp`)**: Points to the base of the current function's activation record on the operand stack.
   - `stack[bp + 0 ... bp + num_params - 1]`: Function arguments.
   - `stack[bp + num_params ... bp + num_params + num_locals - 1]`: Local variables.
5. **Flat Memory (`memory`)**: Contiguous 64-bit word array where global fixed-size arrays reside.
   - Global arrays are placed sequentially with padding before, between, and after arrays.
   - Padding ensures that moderate out-of-bounds accesses in unchecked mode corrupt adjacent padding/data silently without faulting the host process.

---

## 2. Instruction Format

Every instruction occupies exactly **3 words** (24 bytes in 64-bit machine words):
```c
typedef struct {
    int64_t opcode;  /* Opcode ID */
    int64_t a;       /* Primary operand (immediate, slot, target, or array ID) */
    int64_t b;       /* Secondary operand (argument count, etc.) */
} Instruction;
```

---

## 3. Instruction Set Summary

| Opcode | Mnemonic | Operands | Stack Transition | Description |
|---|---|---|---|---|
| 0 | `NOP` | — | `[...] -> [...]` | No operation. |
| 1 | `PUSH` | `imm` | `[...] -> [..., imm]` | Push immediate integer constant `imm`. |
| 2 | `POP` | — | `[..., x] -> [...]` | Pop and discard the top stack element. |
| 3 | `DUP` | — | `[..., x] -> [..., x, x]` | Duplicate the top stack element. |
| 4 | `LOAD` | `slot` | `[...] -> [..., stack[bp + slot]]` | Push local variable or parameter at `bp + slot`. |
| 5 | `STORE` | `slot` | `[..., v] -> [...]` | Pop `v` and write to `stack[bp + slot]`. |
| 6 | `ADD` | — | `[..., x, y] -> [..., x + y]` | Integer addition. |
| 7 | `SUB` | — | `[..., x, y] -> [..., x - y]` | Integer subtraction (`x - y`). |
| 8 | `MUL` | — | `[..., x, y] -> [..., x * y]` | Integer multiplication. |
| 9 | `DIV` | — | `[..., x, y] -> [..., x / y]` | Truncating integer division (`x / y`). Traps if `y == 0`. |
| 10 | `MOD` | — | `[..., x, y] -> [..., x % y]` | C-style remainder (`x % y`). Traps if `y == 0`. |
| 11 | `NEG` | — | `[..., x] -> [..., -x]` | Unary arithmetic negation. |
| 12 | `EQ` | — | `[..., x, y] -> [..., x == y ? 1 : 0]` | Equality test. |
| 13 | `NE` | — | `[..., x, y] -> [..., x != y ? 1 : 0]` | Inequality test. |
| 14 | `LT` | — | `[..., x, y] -> [..., x < y ? 1 : 0]` | Signed less-than test. |
| 15 | `LE` | — | `[..., x, y] -> [..., x <= y ? 1 : 0]` | Signed less-than-or-equal test. |
| 16 | `GT` | — | `[..., x, y] -> [..., x > y ? 1 : 0]` | Signed greater-than test. |
| 17 | `GE` | — | `[..., x, y] -> [..., x >= y ? 1 : 0]` | Signed greater-than-or-equal test. |
| 18 | `NOT` | — | `[..., x] -> [..., x == 0 ? 1 : 0]` | Logical NOT. |
| 19 | `JMP` | `target` | `[...] -> [...]` | Unconditional jump to `target`. |
| 20 | `JZ` | `target` | `[..., c] -> [...]` | Pop `c`. Jump to `target` if `c == 0`. |
| 21 | `JNZ` | `target` | `[..., c] -> [...]` | Pop `c`. Jump to `target` if `c != 0`. |
| 22 | `CALL` | `target, nargs` | `[..., arg0, ..., argN-1] -> [...]` | Push frame (`ret_pc = pc + 1, prev_bp = bp`), `bp = sp - nargs`, `pc = target`. |
| 23 | `ENTER` | `nlocals` | `[...] -> [..., 0 * nlocals]` | Allocate `nlocals` zeroed slots on operand stack. |
| 24 | `RET` | — | `[..., v] -> [..., v]` | Pop `v`, restore `sp = bp`, restore caller frame (`bp, pc`), push `v`. If top-level, halt. |
| 25 | `PRINT` | — | `[..., v] -> [...]` | Pop `v` and print formatted as `%ld\n` to stdout. |
| 26 | `HALT` | — | `[...] -> [...]` | Terminate execution with exit status 0. |
| 27 | `ALOAD` | `arr_id` | `[..., idx] -> [..., memory[base + idx]]` | Unchecked array load. |
| 28 | `ASTORE` | `arr_id` | `[..., v, idx] -> [...]` | Unchecked array store `memory[base + idx] = v`. |
| 29 | `CHK` | `arr_id` | `[..., idx] -> [..., idx]` | Check bounds: trap unless `0 <= idx < |arr|` (single unsigned comparison `(uint64_t)idx < (uint64_t)len`). Does **not** pop `idx`. |
| 30 | `ALOADC` | `arr_id` | `[..., idx] -> [..., memory[base + idx]]` | Fused bounds check and load: trap unless `0 <= idx < |arr|`, then pop `idx` and push loaded element. |
| 31 | `ASTOREC` | `arr_id` | `[..., v, idx] -> [...]` | Fused bounds check and store: trap unless `0 <= idx < |arr|`, then pop `idx`, pop `v`, and write `memory[base + idx] = v`. |

---

## 4. Safety and Bounds Checking

### 4.1 Check Evaluation
Given array `arr` of length `len = |arr|`:
A check tests `(uint64_t)idx < (uint64_t)len`. If false, a bounds check trap occurs.

### 4.2 Trap Behavior
When a bounds check fails in `CHK`, `ALOADC`, or `ASTOREC`:
- The VM immediately halts with exit code `2`.
- A diagnostic message is emitted to `stderr`:
  ```text
  TRAP: bounds check failed for array '<name>' at pc <pc> (index <idx>, size <len>)
  ```

### 4.3 Pad Memory
Arrays are allocated sequentially in `memory` with inter-array and end-of-array padding (e.g. 128 words). In mode `U` (unchecked), an access out-of-bounds reads or writes to the adjacent padding or array, silently corrupting data without raising host faults.

---

## 5. Compilation Modes

The compiler emits instructions based on the `--mode` flag:

- **Mode `U` (Unchecked)**:
  - Load: `ALOAD arr_id`
  - Store: `ASTORE arr_id`
- **Mode `R` (Runtime-checked)**:
  - Load: `CHK arr_id` followed by `ALOAD arr_id`
  - Store: `CHK arr_id` followed by `ASTORE arr_id`
- **Mode `F` (Fused checks)**:
  - Load: `ALOADC arr_id`
  - Store: `ASTOREC arr_id`
- **Mode `S` (Static interval analysis)**:
  - Safe site: `ALOAD` / `ASTORE` (omit `CHK`)
  - Unproven site: `CHK` followed by `ALOAD` / `ASTORE`
- **Mode `H` (Static analysis + Loop-guard hoisting)**:
  - Same as `S`, but innermost loops with loop-invariant parameter bounds are versioned with a hoisted pre-loop guard.
- **Modes `FS` and `FH` (Future extension)**:
  - Fused check `ALOADC`/`ASTOREC` only at sites not proven safe.

---

## 6. Interpreter Dispatch Architecture

The VM interpreter loop supports compile-time selectable dispatch via `-DDISPATCH=SWITCH` or `-DDISPATCH=GOTO`:

1. **`SWITCH` Dispatch**:
   Traditional `switch (code[pc].opcode)` inside an execution loop.
2. **`GOTO` (Computed Goto, Default)**:
   GCC `&&label` computed goto table: `goto *dispatch_table[code[pc].opcode]`. Each instruction body ends with `DISPATCH_NEXT()`.
3. **Extensibility**:
   Designed to accommodate direct-threaded dispatch (replacing opcode values with code labels directly) in future extensions without altering instruction semantics.

### 6.1 Timing Measurement
Wall-clock time of the interpreter loop only is measured using `clock_gettime(CLOCK_MONOTONIC, ...)` strictly surrounding the instruction dispatch loop (excluding VM startup, bytecode loading, and shutdown). The time is reported on `stderr` via:
```text
TIME_NS: <elapsed_nanoseconds>
TIME_S: <elapsed_seconds>
```

### 6.2 Instrumentation Mode (`-DCOUNT`)
When compiled with `-DCOUNT`, the VM maintains:
- `total_instructions`: Count of all executed instructions.
- `total_checks`: Count of all bounds checks executed (`CHK`, `ALOADC`, `ASTOREC`).
At VM exit, it reports to `stderr`:
```text
INSTR_COUNT: <total_instructions>
CHECK_COUNT: <total_checks>
```

---

## 7. Bytecode Binary File Format (`.mbc`)

Bytecode files use the following binary format (little-endian):

```text
Header:
  [8 bytes] Magic: 'M', 'I', 'N', 'I', 'L', 'B', '0', '1'
  [4 bytes] uint32_t num_arrays
  [4 bytes] uint32_t entry_pc
  [4 bytes] uint32_t num_instructions
  [4 bytes] uint32_t reserved (0)

Array Table (num_arrays entries):
  [32 bytes] char name[32] (null-terminated string)
  [8 bytes]  int64_t length
  [8 bytes]  int64_t base_offset

Instruction Stream (num_instructions entries):
  [8 bytes]  int64_t opcode
  [8 bytes]  int64_t a
  [8 bytes]  int64_t b
```
