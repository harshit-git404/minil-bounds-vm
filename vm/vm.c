#define _POSIX_C_SOURCE 199309L
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>

#if defined(__x86_64__) || defined(_M_X64)
#include <x86intrin.h>
#define HAS_RDTSC 1
#endif
#include "vm.h"

#define DISPATCH_SWITCH 1
#define DISPATCH_GOTO   2
#define DISPATCH_DIRECT 3

#ifndef SWITCH
#define SWITCH DISPATCH_SWITCH
#endif

#ifndef GOTO
#define GOTO DISPATCH_GOTO
#endif

#ifndef DIRECT
#define DIRECT DISPATCH_DIRECT
#endif

#ifndef DISPATCH
#define DISPATCH GOTO
#endif

/* Global VM State */
static Instruction *code = NULL;
static uint32_t num_instructions = 0;
static uint32_t entry_pc = 0;

static ArrayDescriptor *arrays = NULL;
static uint32_t num_arrays = 0;

static int64_t *memory = NULL;
static size_t memory_words = 0;

static int64_t stack[STACK_CAPACITY];
static int64_t sp = 0;

static CallFrame call_stack[CALL_STACK_CAPACITY];
static int64_t call_sp = 0;
static int64_t bp = 0;

#ifdef COUNT
static uint64_t total_instructions = 0;
static uint64_t total_checks = 0;
#endif

static void print_counts(void) {
#ifdef COUNT
    fprintf(stderr, "INSTR_COUNT: %llu\nCHECK_COUNT: %llu\n",
            (unsigned long long)total_instructions,
            (unsigned long long)total_checks);
#endif
}

static void trap_bounds(int64_t pc, int64_t arr_id, int64_t idx, int64_t site_id) {
    const char *arr_name = (arr_id >= 0 && (uint32_t)arr_id < num_arrays) ? arrays[arr_id].name : "unknown";
    int64_t len = (arr_id >= 0 && (uint32_t)arr_id < num_arrays) ? arrays[arr_id].length : -1;
    fprintf(stderr, "TRAP: bounds check failed for array '%s' at pc %ld, site %ld (index %ld, size %ld)\n",
            arr_name, (long)pc, (long)site_id, (long)idx, (long)len);
    print_counts();
    exit(2);
}

static void runtime_error(const char *msg, int64_t pc) {
    fprintf(stderr, "RUNTIME ERROR at pc %ld: %s\n", (long)pc, msg);
    print_counts();
    exit(3);
}

static void load_bytecode(const char *filepath) {
    FILE *f = fopen(filepath, "rb");
    if (!f) {
        perror("Failed to open bytecode file");
        exit(1);
    }

    char magic[8];
    if (fread(magic, 1, 8, f) != 8 || memcmp(magic, MINIL_MAGIC, 8) != 0) {
        fprintf(stderr, "Error: Invalid bytecode magic header\n");
        fclose(f);
        exit(1);
    }

    uint32_t reserved = 0;
    if (fread(&num_arrays, sizeof(uint32_t), 1, f) != 1 ||
        fread(&entry_pc, sizeof(uint32_t), 1, f) != 1 ||
        fread(&num_instructions, sizeof(uint32_t), 1, f) != 1 ||
        fread(&reserved, sizeof(uint32_t), 1, f) != 1) {
        fprintf(stderr, "Error reading bytecode header\n");
        fclose(f);
        exit(1);
    }

    if (num_arrays > 0) {
        arrays = (ArrayDescriptor *)malloc(sizeof(ArrayDescriptor) * num_arrays);
        if (!arrays) {
            fprintf(stderr, "Out of memory allocating array descriptors\n");
            fclose(f);
            exit(1);
        }
        for (uint32_t i = 0; i < num_arrays; i++) {
            if (fread(arrays[i].name, 1, 32, f) != 32 ||
                fread(&arrays[i].length, sizeof(int64_t), 1, f) != 1 ||
                fread(&arrays[i].base_offset, sizeof(int64_t), 1, f) != 1) {
                fprintf(stderr, "Error reading array descriptor %u\n", i);
                fclose(f);
                exit(1);
            }
        }
    }

    if (num_instructions > 0) {
        code = (Instruction *)malloc(sizeof(Instruction) * num_instructions);
        if (!code) {
            fprintf(stderr, "Out of memory allocating instruction memory\n");
            fclose(f);
            exit(1);
        }
        for (uint32_t i = 0; i < num_instructions; i++) {
            if (fread(&code[i].opcode, sizeof(int64_t), 1, f) != 1 ||
                fread(&code[i].a, sizeof(int64_t), 1, f) != 1 ||
                fread(&code[i].b, sizeof(int64_t), 1, f) != 1) {
                fprintf(stderr, "Error reading instruction %u\n", i);
                fclose(f);
                exit(1);
            }
        }
    }

    fclose(f);

    /* Allocate flat memory with padding */
    int64_t max_needed = 0;
    for (uint32_t i = 0; i < num_arrays; i++) {
        int64_t end = arrays[i].base_offset + arrays[i].length + 1024;
        if (end > max_needed) {
            max_needed = end;
        }
    }
    memory_words = (size_t)max_needed + INITIAL_MEMORY_CAPACITY;
    memory = (int64_t *)calloc(memory_words, sizeof(int64_t));
    if (!memory) {
        fprintf(stderr, "Out of memory allocating VM memory region\n");
        exit(1);
    }
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <bytecode_file.mbc>\n", argv[0]);
        return 1;
    }

    load_bytecode(argv[1]);

    int64_t pc = entry_pc;
    sp = 0;
    call_sp = 0;
    bp = 0;

    struct timespec start_time, end_time;

#ifdef HAS_RDTSC
    uint64_t rdtsc_start = __rdtsc();
#endif

    /* Measure wall-clock time strictly around interpreter loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);

#if DISPATCH == DISPATCH_GOTO

    static const void *dispatch_table[NUM_OPCODES] = {
        [OP_NOP]     = &&do_NOP,
        [OP_PUSH]    = &&do_PUSH,
        [OP_POP]     = &&do_POP,
        [OP_DUP]     = &&do_DUP,
        [OP_LOAD]    = &&do_LOAD,
        [OP_STORE]   = &&do_STORE,
        [OP_ADD]     = &&do_ADD,
        [OP_SUB]     = &&do_SUB,
        [OP_MUL]     = &&do_MUL,
        [OP_DIV]     = &&do_DIV,
        [OP_MOD]     = &&do_MOD,
        [OP_NEG]     = &&do_NEG,
        [OP_EQ]      = &&do_EQ,
        [OP_NE]      = &&do_NE,
        [OP_LT]      = &&do_LT,
        [OP_LE]      = &&do_LE,
        [OP_GT]      = &&do_GT,
        [OP_GE]      = &&do_GE,
        [OP_NOT]     = &&do_NOT,
        [OP_JMP]     = &&do_JMP,
        [OP_JZ]      = &&do_JZ,
        [OP_JNZ]     = &&do_JNZ,
        [OP_CALL]    = &&do_CALL,
        [OP_ENTER]   = &&do_ENTER,
        [OP_RET]     = &&do_RET,
        [OP_PRINT]   = &&do_PRINT,
        [OP_HALT]    = &&do_HALT,
        [OP_ALOAD]   = &&do_ALOAD,
        [OP_ASTORE]  = &&do_ASTORE,
        [OP_CHK]     = &&do_CHK,
        [OP_ALOADC]  = &&do_ALOADC,
        [OP_ASTOREC] = &&do_ASTOREC,
#ifdef EXPERIMENTAL_DECOMP
        [OP_NOPCHK]  = &&do_NOPCHK,
        [OP_ALOADN]  = &&do_ALOADN,
        [OP_ASTOREN] = &&do_ASTOREN,
#endif
    };

#ifdef COUNT
#define DISPATCH_INSN() do { \
    total_instructions++; \
    goto *dispatch_table[code[pc].opcode]; \
} while (0)
#else
#define DISPATCH_INSN() goto *dispatch_table[code[pc].opcode]
#endif

    DISPATCH_INSN();

#define TARGET(op) do_##op:
#define DISPATCH_NEXT() DISPATCH_INSN()

#elif DISPATCH == DISPATCH_DIRECT

    static const void *dispatch_table[NUM_OPCODES] = {
        [OP_NOP]     = &&do_NOP,
        [OP_PUSH]    = &&do_PUSH,
        [OP_POP]     = &&do_POP,
        [OP_DUP]     = &&do_DUP,
        [OP_LOAD]    = &&do_LOAD,
        [OP_STORE]   = &&do_STORE,
        [OP_ADD]     = &&do_ADD,
        [OP_SUB]     = &&do_SUB,
        [OP_MUL]     = &&do_MUL,
        [OP_DIV]     = &&do_DIV,
        [OP_MOD]     = &&do_MOD,
        [OP_NEG]     = &&do_NEG,
        [OP_EQ]      = &&do_EQ,
        [OP_NE]      = &&do_NE,
        [OP_LT]      = &&do_LT,
        [OP_LE]      = &&do_LE,
        [OP_GT]      = &&do_GT,
        [OP_GE]      = &&do_GE,
        [OP_NOT]     = &&do_NOT,
        [OP_JMP]     = &&do_JMP,
        [OP_JZ]      = &&do_JZ,
        [OP_JNZ]     = &&do_JNZ,
        [OP_CALL]    = &&do_CALL,
        [OP_ENTER]   = &&do_ENTER,
        [OP_RET]     = &&do_RET,
        [OP_PRINT]   = &&do_PRINT,
        [OP_HALT]    = &&do_HALT,
        [OP_ALOAD]   = &&do_ALOAD,
        [OP_ASTORE]  = &&do_ASTORE,
        [OP_CHK]     = &&do_CHK,
        [OP_ALOADC]  = &&do_ALOADC,
        [OP_ASTOREC] = &&do_ASTOREC,
#ifdef EXPERIMENTAL_DECOMP
        [OP_NOPCHK]  = &&do_NOPCHK,
        [OP_ALOADN]  = &&do_ALOADN,
        [OP_ASTOREN] = &&do_ASTOREN,
#endif
    };

    const void **direct_table = (const void **)malloc(sizeof(const void *) * (num_instructions + 1));
    for (uint32_t i = 0; i < num_instructions; i++) {
        direct_table[i] = dispatch_table[code[i].opcode];
    }
    direct_table[num_instructions] = &&do_HALT;

#ifdef COUNT
#define DISPATCH_INSN() do { \
    total_instructions++; \
    goto *direct_table[pc]; \
} while (0)
#else
#define DISPATCH_INSN() goto *direct_table[pc]
#endif

    DISPATCH_INSN();

#define TARGET(op) do_##op:
#define DISPATCH_NEXT() DISPATCH_INSN()

#elif DISPATCH == DISPATCH_SWITCH

#define TARGET(op) case OP_##op:
#define DISPATCH_NEXT() break

    while (pc < num_instructions) {
#ifdef COUNT
        total_instructions++;
#endif
        switch (code[pc].opcode) {

#endif /* DISPATCH */

    TARGET(NOP) {
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(PUSH) {
        stack[sp++] = code[pc].a;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(POP) {
        sp--;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(DUP) {
        int64_t v = stack[sp - 1];
        stack[sp++] = v;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(LOAD) {
        stack[sp++] = stack[bp + code[pc].a];
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(STORE) {
        stack[bp + code[pc].a] = stack[--sp];
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(ADD) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = a_val + b_val;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(SUB) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = a_val - b_val;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(MUL) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = a_val * b_val;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(DIV) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        if (b_val == 0) {
            runtime_error("Division by zero", pc);
        }
        stack[sp++] = a_val / b_val;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(MOD) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        if (b_val == 0) {
            runtime_error("Modulo by zero", pc);
        }
        stack[sp++] = a_val % b_val;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(NEG) {
        stack[sp - 1] = -stack[sp - 1];
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(EQ) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = (a_val == b_val) ? 1 : 0;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(NE) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = (a_val != b_val) ? 1 : 0;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(LT) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = (a_val < b_val) ? 1 : 0;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(LE) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = (a_val <= b_val) ? 1 : 0;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(GT) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = (a_val > b_val) ? 1 : 0;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(GE) {
        int64_t b_val = stack[--sp];
        int64_t a_val = stack[--sp];
        stack[sp++] = (a_val >= b_val) ? 1 : 0;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(NOT) {
        stack[sp - 1] = (stack[sp - 1] == 0) ? 1 : 0;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(JMP) {
        pc = code[pc].a;
        DISPATCH_NEXT();
    }

    TARGET(JZ) {
        int64_t cond = stack[--sp];
        if (cond == 0) {
            pc = code[pc].a;
        } else {
            pc++;
        }
        DISPATCH_NEXT();
    }

    TARGET(JNZ) {
        int64_t cond = stack[--sp];
        if (cond != 0) {
            pc = code[pc].a;
        } else {
            pc++;
        }
        DISPATCH_NEXT();
    }

    TARGET(CALL) {
        call_stack[call_sp].ret_pc = pc + 1;
        call_stack[call_sp].prev_bp = bp;
        call_sp++;
        int64_t nargs = code[pc].b;
        bp = sp - nargs;
        pc = code[pc].a;
        DISPATCH_NEXT();
    }

    TARGET(ENTER) {
        int64_t nlocals = code[pc].a;
        for (int64_t i = 0; i < nlocals; i++) {
            stack[sp + i] = 0;
        }
        sp += nlocals;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(RET) {
        int64_t ret_val = stack[--sp];
        sp = bp;
        if (call_sp == 0) {
            goto end_loop;
        }
        call_sp--;
        pc = call_stack[call_sp].ret_pc;
        bp = call_stack[call_sp].prev_bp;
        stack[sp++] = ret_val;
        DISPATCH_NEXT();
    }

    TARGET(PRINT) {
        int64_t val = stack[--sp];
        printf("%ld\n", (long)val);
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(HALT) {
        goto end_loop;
    }

    TARGET(ALOAD) {
        int64_t arr_id = code[pc].a;
        int64_t idx = stack[--sp];
        stack[sp++] = memory[arrays[arr_id].base_offset + idx];
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(ASTORE) {
        int64_t arr_id = code[pc].a;
        int64_t idx = stack[--sp];
        int64_t val = stack[--sp];
        memory[arrays[arr_id].base_offset + idx] = val;
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(CHK) {
#ifdef COUNT
        total_checks++;
#endif
        int64_t arr_id = code[pc].a;
        int64_t idx = stack[sp - 1]; /* Does NOT pop */
        if ((uint64_t)idx >= (uint64_t)arrays[arr_id].length) {
            trap_bounds(pc, arr_id, idx, code[pc].b);
        }
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(ALOADC) {
#ifdef COUNT
        total_checks++;
#endif
        int64_t arr_id = code[pc].a;
        int64_t idx = stack[--sp];
        if ((uint64_t)idx >= (uint64_t)arrays[arr_id].length) {
            trap_bounds(pc, arr_id, idx, code[pc].b);
        }
        stack[sp++] = memory[arrays[arr_id].base_offset + idx];
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(ASTOREC) {
#ifdef COUNT
        total_checks++;
#endif
        int64_t arr_id = code[pc].a;
        int64_t idx = stack[--sp];
        int64_t val = stack[--sp];
        if ((uint64_t)idx >= (uint64_t)arrays[arr_id].length) {
            trap_bounds(pc, arr_id, idx, code[pc].b);
        }
        memory[arrays[arr_id].base_offset + idx] = val;
        pc++;
        DISPATCH_NEXT();
    }

#ifdef EXPERIMENTAL_DECOMP
    TARGET(NOPCHK) {
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(ALOADN) {
        int64_t arr_id = code[pc].a;
        int64_t idx = stack[--sp];
        stack[sp++] = memory[arrays[arr_id].base_offset + idx];
        pc++;
        DISPATCH_NEXT();
    }

    TARGET(ASTOREN) {
        int64_t arr_id = code[pc].a;
        int64_t idx = stack[--sp];
        int64_t val = stack[--sp];
        memory[arrays[arr_id].base_offset + idx] = val;
        pc++;
        DISPATCH_NEXT();
    }
#endif

#if DISPATCH == DISPATCH_SWITCH
        default:
            runtime_error("Invalid opcode", pc);
            break;
        }
    }
#endif

end_loop:
    clock_gettime(CLOCK_MONOTONIC, &end_time);
#ifdef HAS_RDTSC
    uint64_t rdtsc_end = __rdtsc();
    uint64_t rdtsc_cycles = rdtsc_end - rdtsc_start;
    fprintf(stderr, "RDTSC_CYCLES: %llu\n", (unsigned long long)rdtsc_cycles);
#endif

    long long elapsed_ns = (end_time.tv_sec - start_time.tv_sec) * 1000000000LL +
                           (end_time.tv_nsec - start_time.tv_nsec);
    fprintf(stderr, "TIME_NS: %lld\nTIME_S: %.9f\n", elapsed_ns, (double)elapsed_ns / 1e9);

    print_counts();

    free(memory);
    free(code);
    free(arrays);
#if DISPATCH == DISPATCH_DIRECT
    free((void *)direct_table);
#endif

    return 0;
}
