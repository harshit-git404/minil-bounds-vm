"""
MiniL Virtual Machine Instruction Opcodes.
"""
OP_NOP     = 0
OP_PUSH    = 1
OP_POP     = 2
OP_DUP     = 3
OP_LOAD    = 4
OP_STORE   = 5
OP_ADD     = 6
OP_SUB     = 7
OP_MUL     = 8
OP_DIV     = 9
OP_MOD     = 10
OP_NEG     = 11
OP_EQ      = 12
OP_NE      = 13
OP_LT      = 14
OP_LE      = 15
OP_GT      = 16
OP_GE      = 17
OP_NOT     = 18
OP_JMP     = 19
OP_JZ      = 20
OP_JNZ     = 21
OP_CALL    = 22
OP_ENTER   = 23
OP_RET     = 24
OP_PRINT   = 25
OP_HALT    = 26
OP_ALOAD   = 27
OP_ASTORE  = 28
OP_CHK     = 29
OP_ALOADC  = 30
OP_ASTOREC = 31

OPCODE_NAMES = {
    OP_NOP: "NOP",
    OP_PUSH: "PUSH",
    OP_POP: "POP",
    OP_DUP: "DUP",
    OP_LOAD: "LOAD",
    OP_STORE: "STORE",
    OP_ADD: "ADD",
    OP_SUB: "SUB",
    OP_MUL: "MUL",
    OP_DIV: "DIV",
    OP_MOD: "MOD",
    OP_NEG: "NEG",
    OP_EQ: "EQ",
    OP_NE: "NE",
    OP_LT: "LT",
    OP_LE: "LE",
    OP_GT: "GT",
    OP_GE: "GE",
    OP_NOT: "NOT",
    OP_JMP: "JMP",
    OP_JZ: "JZ",
    OP_JNZ: "JNZ",
    OP_CALL: "CALL",
    OP_ENTER: "ENTER",
    OP_RET: "RET",
    OP_PRINT: "PRINT",
    OP_HALT: "HALT",
    OP_ALOAD: "ALOAD",
    OP_ASTORE: "ASTORE",
    OP_CHK: "CHK",
    OP_ALOADC: "ALOADC",
    OP_ASTOREC: "ASTOREC",
}
