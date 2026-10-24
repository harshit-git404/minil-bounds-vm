"""
Bytecode generator for MiniL.
Supports compilation modes: U, R, F, S, H, FS, FH.
"""
import struct
from typing import Dict, List, Optional, Set, Tuple
from compiler.ast_nodes import (
    Program, GlobalArray, FuncDef, Param, Stmt, Expr,
    VarDeclStmt, AssignStmt, ArrayAssignStmt, IfStmt, WhileStmt,
    ReturnStmt, PrintStmt, ExprStmt, BlockStmt,
    IntLit, VarExpr, ArrayAccessExpr, UnaryExpr, BinaryExpr, CallExpr
)
from compiler.opcodes import *
from compiler.sema import Sema

PAD_WORDS = 128

class CodeGenerator:
    def __init__(self, sema: Sema, mode: str = "GOTO", safe_sites: Optional[Set[int]] = None):
        self.sema = sema
        self.mode = mode.upper()
        self.safe_sites = safe_sites if safe_sites is not None else set()

        # Intermediate instruction list: (opcode, a, b) where a/b can be label references
        self.instructions: List[List[any]] = []
        self.labels: Dict[str, int] = {}
        self.fixups: List[Tuple[int, int, str]] = [] # (instr_idx, operand_index, label_name)
        self.label_counter = 0

        # Memory layout for arrays
        self.array_metadata: List[Tuple[str, int, int]] = [] # (name, length, base_offset)
        self._layout_memory()

    def _layout_memory(self):
        curr_offset = PAD_WORDS
        for arr in self.sema.global_arrays.values():
            self.array_metadata.append((arr.name, arr.size, curr_offset))
            curr_offset += arr.size + PAD_WORDS

    def _new_label(self, prefix: str = "L") -> str:
        lbl = f"{prefix}_{self.label_counter}"
        self.label_counter += 1
        return lbl

    def _mark_label(self, name: str):
        self.labels[name] = len(self.instructions)

    def emit(self, opcode: int, a: any = 0, b: any = 0) -> int:
        idx = len(self.instructions)
        self.instructions.append([opcode, a, b])
        return idx

    def emit_jump(self, opcode: int, target_label: str) -> int:
        idx = len(self.instructions)
        self.instructions.append([opcode, 0, 0])
        self.fixups.append((idx, 1, target_label)) # operand 'a' is target
        return idx

    def _emit_array_load(self, arr_id: int, site_id: int):
        if self.mode == "U":
            self.emit(OP_ALOAD, arr_id, 0)
        elif self.mode == "R":
            self.emit(OP_CHK, arr_id, 0)
            self.emit(OP_ALOAD, arr_id, 0)
        elif self.mode == "F":
            self.emit(OP_ALOADC, arr_id, 0)
        elif self.mode in ("S", "H"):
            if site_id in self.safe_sites:
                self.emit(OP_ALOAD, arr_id, 0)
            else:
                self.emit(OP_CHK, arr_id, 0)
                self.emit(OP_ALOAD, arr_id, 0)
        elif self.mode in ("FS", "FH"):
            if site_id in self.safe_sites:
                self.emit(OP_ALOAD, arr_id, 0)
            else:
                self.emit(OP_ALOADC, arr_id, 0)
        else:
            raise ValueError(f"Unknown compilation mode: {self.mode}")

    def _emit_array_store(self, arr_id: int, site_id: int):
        if self.mode == "U":
            self.emit(OP_ASTORE, arr_id, 0)
        elif self.mode == "R":
            self.emit(OP_CHK, arr_id, 0)
            self.emit(OP_ASTORE, arr_id, 0)
        elif self.mode == "F":
            self.emit(OP_ASTOREC, arr_id, 0)
        elif self.mode in ("S", "H"):
            if site_id in self.safe_sites:
                self.emit(OP_ASTORE, arr_id, 0)
            else:
                self.emit(OP_CHK, arr_id, 0)
                self.emit(OP_ASTORE, arr_id, 0)
        elif self.mode in ("FS", "FH"):
            if site_id in self.safe_sites:
                self.emit(OP_ASTORE, arr_id, 0)
            else:
                self.emit(OP_ASTOREC, arr_id, 0)
        else:
            raise ValueError(f"Unknown compilation mode: {self.mode}")

    def generate(self, program: Program) -> List[Tuple[int, int, int]]:
        self.instructions.clear()
        self.labels.clear()
        self.fixups.clear()

        # Bootstrap: call main(), then halt
        main_sym = self.sema.functions["main"]
        self.emit_jump(OP_CALL, "func_main")
        # CALL target, nargs
        # b is nargs = 0
        self.instructions[-1][2] = 0
        self.emit(OP_HALT, 0, 0)

        # Generate each function
        for func in program.functions:
            self._generate_function(func)

        # Backpatch jump targets
        for instr_idx, op_idx, label_name in self.fixups:
            if label_name not in self.labels:
                raise RuntimeError(f"Unresolved label: {label_name}")
            target_pc = self.labels[label_name]
            self.instructions[instr_idx][op_idx] = target_pc

        return [tuple(instr) for instr in self.instructions]

    def _generate_function(self, func: FuncDef):
        func_sym = self.sema.functions[func.name]
        self._mark_label(f"func_{func.name}")

        # ENTER nlocals
        self.emit(OP_ENTER, func_sym.num_locals, 0)

        # Generate statements
        has_return = False
        for stmt in func.body:
            self._generate_stmt(stmt, func_sym)
            if isinstance(stmt, ReturnStmt):
                has_return = True

        # If function doesn't end with return, emit default return 0
        if not has_return:
            self.emit(OP_PUSH, 0, 0)
            self.emit(OP_RET, 0, 0)

    def _generate_stmt(self, stmt: Stmt, func_sym):
        if isinstance(stmt, VarDeclStmt):
            slot = func_sym.slots[stmt.name]
            if stmt.init_expr is not None:
                self._generate_expr(stmt.init_expr, func_sym)
                self.emit(OP_STORE, slot, 0)

        elif isinstance(stmt, AssignStmt):
            slot = func_sym.slots[stmt.name]
            self._generate_expr(stmt.expr, func_sym)
            self.emit(OP_STORE, slot, 0)

        elif isinstance(stmt, ArrayAssignStmt):
            arr_id = self.sema.global_array_indices[stmt.name]
            # Stack layout for ASTORE / ASTOREC:
            # 1. evaluate rhs value -> pushes val
            self._generate_expr(stmt.expr, func_sym)
            # 2. evaluate index -> pushes idx
            self._generate_expr(stmt.index_expr, func_sym)
            # Stack is [..., val, idx]
            self._emit_array_store(arr_id, stmt.site_id)

        elif isinstance(stmt, IfStmt):
            else_lbl = self._new_label("else")
            end_lbl = self._new_label("endif")

            self._generate_expr(stmt.cond, func_sym)
            self.emit_jump(OP_JZ, else_lbl)

            self._generate_stmt(stmt.then_branch, func_sym)
            if stmt.else_branch is not None:
                self.emit_jump(OP_JMP, end_lbl)
                self._mark_label(else_lbl)
                self._generate_stmt(stmt.else_branch, func_sym)
                self._mark_label(end_lbl)
            else:
                self._mark_label(else_lbl)

        elif isinstance(stmt, WhileStmt):
            loop_start = self._new_label("while_start")
            loop_end = self._new_label("while_end")

            self._mark_label(loop_start)
            self._generate_expr(stmt.cond, func_sym)
            self.emit_jump(OP_JZ, loop_end)

            self._generate_stmt(stmt.body, func_sym)
            self.emit_jump(OP_JMP, loop_start)

            self._mark_label(loop_end)

        elif isinstance(stmt, ReturnStmt):
            self._generate_expr(stmt.expr, func_sym)
            self.emit(OP_RET, 0, 0)

        elif isinstance(stmt, PrintStmt):
            self._generate_expr(stmt.expr, func_sym)
            self.emit(OP_PRINT, 0, 0)

        elif isinstance(stmt, ExprStmt):
            self._generate_expr(stmt.expr, func_sym)
            self.emit(OP_POP, 0, 0)

        elif isinstance(stmt, BlockStmt):
            for s in stmt.stmts:
                self._generate_stmt(s, func_sym)

    def _generate_expr(self, expr: Expr, func_sym):
        if isinstance(expr, IntLit):
            self.emit(OP_PUSH, expr.val, 0)

        elif isinstance(expr, VarExpr):
            slot = func_sym.slots[expr.name]
            self.emit(OP_LOAD, slot, 0)

        elif isinstance(expr, ArrayAccessExpr):
            arr_id = self.sema.global_array_indices[expr.name]
            # 1. evaluate index -> pushes idx
            self._generate_expr(expr.index_expr, func_sym)
            # Stack is [..., idx]
            self._emit_array_load(arr_id, expr.site_id)

        elif isinstance(expr, UnaryExpr):
            self._generate_expr(expr.expr, func_sym)
            if expr.op == "-":
                self.emit(OP_NEG, 0, 0)
            elif expr.op == "!":
                self.emit(OP_NOT, 0, 0)

        elif isinstance(expr, BinaryExpr):
            if expr.op == "&&":
                false_lbl = self._new_label("and_false")
                end_lbl = self._new_label("and_end")
                self._generate_expr(expr.left, func_sym)
                self.emit_jump(OP_JZ, false_lbl)
                self._generate_expr(expr.right, func_sym)
                self.emit_jump(OP_JZ, false_lbl)
                self.emit(OP_PUSH, 1, 0)
                self.emit_jump(OP_JMP, end_lbl)
                self._mark_label(false_lbl)
                self.emit(OP_PUSH, 0, 0)
                self._mark_label(end_lbl)

            elif expr.op == "||":
                true_lbl = self._new_label("or_true")
                end_lbl = self._new_label("or_end")
                self._generate_expr(expr.left, func_sym)
                self.emit_jump(OP_JNZ, true_lbl)
                self._generate_expr(expr.right, func_sym)
                self.emit_jump(OP_JNZ, true_lbl)
                self.emit(OP_PUSH, 0, 0)
                self.emit_jump(OP_JMP, end_lbl)
                self._mark_label(true_lbl)
                self.emit(OP_PUSH, 1, 0)
                self._mark_label(end_lbl)

            else:
                self._generate_expr(expr.left, func_sym)
                self._generate_expr(expr.right, func_sym)
                op_map = {
                    "+": OP_ADD,
                    "-": OP_SUB,
                    "*": OP_MUL,
                    "/": OP_DIV,
                    "%": OP_MOD,
                    "==": OP_EQ,
                    "!=": OP_NE,
                    "<": OP_LT,
                    "<=": OP_LE,
                    ">": OP_GT,
                    ">=": OP_GE,
                }
                if expr.op in op_map:
                    self.emit(op_map[expr.op], 0, 0)
                else:
                    raise RuntimeError(f"Unknown binary operator: {expr.op}")

        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._generate_expr(arg, func_sym)
            self.emit_jump(OP_CALL, f"func_{expr.name}")
            # b is number of arguments
            self.instructions[-1][2] = len(expr.args)

    def write_bytecode(self, filepath: str):
        """
        Serializes bytecode according to docs/isa.md:
        Header:
          [8 bytes] Magic: 'MINILB01'
          [4 bytes] uint32_t num_arrays
          [4 bytes] uint32_t entry_pc (0)
          [4 bytes] uint32_t num_instructions
          [4 bytes] uint32_t reserved (0)
        Array Table:
          For each array:
            [32 bytes] char name[32] (null-terminated)
            [8 bytes]  int64_t length
            [8 bytes]  int64_t base_offset
        Instruction Stream:
          For each instruction:
            [8 bytes]  int64_t opcode
            [8 bytes]  int64_t a
            [8 bytes]  int64_t b
        """
        magic = b"MINILB01"
        num_arrays = len(self.array_metadata)
        entry_pc = 0
        num_instructions = len(self.instructions)
        reserved = 0

        with open(filepath, "wb") as f:
            # Header
            header = struct.pack("<8sIIII", magic, num_arrays, entry_pc, num_instructions, reserved)
            f.write(header)

            # Array Table
            for name, length, base_offset in self.array_metadata:
                name_bytes = name.encode("utf-8")[:31].ljust(32, b"\x00")
                arr_entry = struct.pack("<32sqq", name_bytes, length, base_offset)
                f.write(arr_entry)

            # Instructions
            for opcode, a, b in self.instructions:
                instr_bytes = struct.pack("<qqq", opcode, a, b)
                f.write(instr_bytes)
