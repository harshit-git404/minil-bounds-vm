"""
Semantic analysis for MiniL:
- Name resolution
- Function arity checks
- Local slot allocation
- Compile-time bounds violation diagnostics
"""
import sys
from typing import Dict, List, Optional, Tuple
from compiler.ast_nodes import (
    Program, GlobalArray, FuncDef, Param, Stmt, Expr,
    VarDeclStmt, AssignStmt, ArrayAssignStmt, IfStmt, WhileStmt,
    ReturnStmt, PrintStmt, ExprStmt, BlockStmt,
    IntLit, VarExpr, ArrayAccessExpr, UnaryExpr, BinaryExpr, CallExpr
)

class SemaError(Exception):
    def __init__(self, message: str, line: int = 0, col: int = 0):
        super().__init__(f"Semantic error at line {line}, col {col}: {message}")
        self.line = line
        self.col = col

class FunctionSymbol:
    def __init__(self, name: str, params: List[str], func_def: FuncDef):
        self.name = name
        self.params = params
        self.func_def = func_def
        self.num_params = len(params)
        self.num_locals = 0
        # maps var_name -> slot index
        self.slots: Dict[str, int] = {}

class Sema:
    def __init__(self):
        self.global_arrays: Dict[str, GlobalArray] = {}
        self.global_array_indices: Dict[str, int] = {}
        self.functions: Dict[str, FunctionSymbol] = {}
        self.current_func: Optional[FunctionSymbol] = None
        self.diagnostics: List[str] = []

    def analyze(self, program: Program) -> None:
        self.diagnostics.clear()

        # 1. Register global arrays
        for idx, arr in enumerate(program.global_arrays):
            if arr.name in self.global_arrays:
                raise SemaError(f"Duplicate global array declaration '{arr.name}'", arr.line, arr.col)
            self.global_arrays[arr.name] = arr
            self.global_array_indices[arr.name] = idx

        # 2. Register functions
        for func in program.functions:
            if func.name in self.functions:
                raise SemaError(f"Duplicate function definition '{func.name}'", func.line, func.col)
            if func.name in self.global_arrays:
                raise SemaError(f"Function name '{func.name}' collides with global array", func.line, func.col)

            param_names = []
            for p in func.params:
                if p.name in param_names:
                    raise SemaError(f"Duplicate parameter name '{p.name}' in function '{func.name}'", p.line, p.col)
                param_names.append(p.name)

            func_sym = FunctionSymbol(func.name, param_names, func)
            # Allocate slots for parameters: 0 .. num_params - 1
            for slot, p_name in enumerate(param_names):
                func_sym.slots[p_name] = slot

            self.functions[func.name] = func_sym

        if "main" not in self.functions:
            raise SemaError("Program missing 'main' function")

        # 3. Analyze each function body
        for func in program.functions:
            self.current_func = self.functions[func.name]
            for stmt in func.body:
                self._analyze_stmt(stmt)

        # Print diagnostics to stderr if any
        for diag in self.diagnostics:
            sys.stderr.write(f"[DIAGNOSTIC] {diag}\n")

    def _analyze_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, VarDeclStmt):
            if stmt.name in self.current_func.slots:
                raise SemaError(f"Variable '{stmt.name}' already declared in function '{self.current_func.name}'", stmt.line, stmt.col)
            if stmt.name in self.global_arrays:
                # Warning or error? In MiniL, local variables can shadow or we can allow/warn.
                pass
            # Allocate local slot
            slot = self.current_func.num_params + self.current_func.num_locals
            self.current_func.slots[stmt.name] = slot
            self.current_func.num_locals += 1

            if stmt.init_expr is not None:
                self._analyze_expr(stmt.init_expr)

        elif isinstance(stmt, AssignStmt):
            if stmt.name not in self.current_func.slots:
                if stmt.name in self.global_arrays:
                    raise SemaError(f"Cannot assign scalar to array '{stmt.name}'", stmt.line, stmt.col)
                raise SemaError(f"Undeclared variable '{stmt.name}'", stmt.line, stmt.col)
            self._analyze_expr(stmt.expr)

        elif isinstance(stmt, ArrayAssignStmt):
            if stmt.name not in self.global_arrays:
                if stmt.name in self.current_func.slots:
                    raise SemaError(f"Cannot index non-array variable '{stmt.name}'", stmt.line, stmt.col)
                raise SemaError(f"Undeclared array '{stmt.name}'", stmt.line, stmt.col)

            self._check_constant_bounds(stmt.name, stmt.index_expr, stmt.line, stmt.col)
            self._analyze_expr(stmt.index_expr)
            self._analyze_expr(stmt.expr)

        elif isinstance(stmt, IfStmt):
            self._analyze_expr(stmt.cond)
            self._analyze_stmt(stmt.then_branch)
            if stmt.else_branch is not None:
                self._analyze_stmt(stmt.else_branch)

        elif isinstance(stmt, WhileStmt):
            self._analyze_expr(stmt.cond)
            self._analyze_stmt(stmt.body)

        elif isinstance(stmt, ReturnStmt):
            self._analyze_expr(stmt.expr)

        elif isinstance(stmt, PrintStmt):
            self._analyze_expr(stmt.expr)

        elif isinstance(stmt, ExprStmt):
            self._analyze_expr(stmt.expr)

        elif isinstance(stmt, BlockStmt):
            for s in stmt.stmts:
                self._analyze_stmt(s)

    def _analyze_expr(self, expr: Expr) -> None:
        if isinstance(expr, IntLit):
            return

        elif isinstance(expr, VarExpr):
            if expr.name not in self.current_func.slots:
                if expr.name in self.global_arrays:
                    raise SemaError(f"Array '{expr.name}' used without index", expr.line, expr.col)
                raise SemaError(f"Undeclared variable '{expr.name}'", expr.line, expr.col)

        elif isinstance(expr, ArrayAccessExpr):
            if expr.name not in self.global_arrays:
                if expr.name in self.current_func.slots:
                    raise SemaError(f"Cannot index non-array variable '{expr.name}'", expr.line, expr.col)
                raise SemaError(f"Undeclared array '{expr.name}'", expr.line, expr.col)

            self._check_constant_bounds(expr.name, expr.index_expr, expr.line, expr.col)
            self._analyze_expr(expr.index_expr)

        elif isinstance(expr, UnaryExpr):
            self._analyze_expr(expr.expr)

        elif isinstance(expr, BinaryExpr):
            self._analyze_expr(expr.left)
            self._analyze_expr(expr.right)

        elif isinstance(expr, CallExpr):
            if expr.name not in self.functions:
                raise SemaError(f"Call to undeclared function '{expr.name}'", expr.line, expr.col)
            callee = self.functions[expr.name]
            if len(expr.args) != callee.num_params:
                raise SemaError(
                    f"Function '{expr.name}' expects {callee.num_params} arguments, got {len(expr.args)}",
                    expr.line, expr.col
                )
            for arg in expr.args:
                self._analyze_expr(arg)

    def _check_constant_bounds(self, arr_name: str, index_expr: Expr, line: int, col: int):
        # Check if index_expr evaluates to a constant integer
        const_val = self._eval_const_expr(index_expr)
        if const_val is not None:
            arr = self.global_arrays[arr_name]
            if const_val < 0 or const_val >= arr.size:
                diag = (f"Compile-time bounds violation: access to array '{arr_name}' at constant "
                        f"index {const_val} is out of bounds [0, {arr.size}) at line {line}, col {col}")
                self.diagnostics.append(diag)

    def _eval_const_expr(self, expr: Expr) -> Optional[int]:
        if isinstance(expr, IntLit):
            return expr.val
        if isinstance(expr, UnaryExpr):
            val = self._eval_const_expr(expr.expr)
            if val is not None:
                if expr.op == "-": return -val
                if expr.op == "+": return val
                if expr.op == "!": return 1 if val == 0 else 0
        if isinstance(expr, BinaryExpr):
            l = self._eval_const_expr(expr.left)
            r = self._eval_const_expr(expr.right)
            if l is not None and r is not None:
                if expr.op == "+": return l + r
                if expr.op == "-": return l - r
                if expr.op == "*": return l * r
                if expr.op == "/" and r != 0: return int(l / r)
                if expr.op == "%" and r != 0: return l % r
        return None
