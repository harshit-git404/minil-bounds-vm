#ifndef MINIL_VM_H
#define MINIL_VM_H

#include <stdint.h>
#include <stddef.h>

#define MINIL_MAGIC "MINILB01"

/* Opcodes */
#define OP_NOP      0
#define OP_PUSH     1
#define OP_POP      2
#define OP_DUP      3
#define OP_LOAD     4
#define OP_STORE    5
#define OP_ADD      6
#define OP_SUB      7
#define OP_MUL      8
#define OP_DIV      9
#define OP_MOD      10
#define OP_NEG      11
#define OP_EQ       12
#define OP_NE       13
#define OP_LT       14
#define OP_LE       15
#define OP_GT       16
#define OP_GE       17
#define OP_NOT      18
#define OP_JMP      19
#define OP_JZ       20
#define OP_JNZ      21
#define OP_CALL     22
#define OP_ENTER    23
#define OP_RET      24
#define OP_PRINT    25
#define OP_HALT     26
#define OP_ALOAD    27
#define OP_ASTORE   28
#define OP_CHK      29
#define OP_ALOADC   30
#define OP_ASTOREC  31

#define NUM_OPCODES 32

/* Fixed-size 3-word instruction */
typedef struct {
    int64_t opcode;
    int64_t a;
    int64_t b;
} Instruction;

/* Array metadata */
typedef struct {
    char name[32];
    int64_t length;
    int64_t base_offset;
} ArrayDescriptor;

/* Call frame */
typedef struct {
    int64_t ret_pc;
    int64_t prev_bp;
} CallFrame;

#define STACK_CAPACITY     (1024 * 1024)   /* 1M 64-bit words */
#define CALL_STACK_CAPACITY (64 * 1024)    /* 64K call frames */
#define INITIAL_MEMORY_CAPACITY (32 * 1024 * 1024) /* 32M 64-bit words */

#endif /* MINIL_VM_H */
