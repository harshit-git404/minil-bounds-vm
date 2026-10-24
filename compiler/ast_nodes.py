"""
MiniL Abstract Syntax Tree (AST) definitions.
"""
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ASTNode:
    line: int = 0
    col: int = 0

@dataclass
class GlobalArray(ASTNode):
    name: str = ""
    size: int = 0

@dataclass
class Param(ASTNode):
    name: str = ""

@dataclass
class Stmt(ASTNode):
    pass

@dataclass
class Expr(ASTNode):
    pass

@dataclass
class VarDeclStmt(Stmt):
    name: str = ""
    init_expr: Optional[Expr] = None

@dataclass
class AssignStmt(Stmt):
    name: str = ""
    expr: Optional[Expr] = None

@dataclass
class ArrayAssignStmt(Stmt):
    name: str = ""
    index_expr: Optional[Expr] = None
    expr: Optional[Expr] = None
    site_id: int = -1

@dataclass
class IfStmt(Stmt):
    cond: Optional[Expr] = None
    then_branch: Optional[Stmt] = None
    else_branch: Optional[Stmt] = None

@dataclass
class WhileStmt(Stmt):
    cond: Optional[Expr] = None
    body: Optional[Stmt] = None

@dataclass
class ReturnStmt(Stmt):
    expr: Optional[Expr] = None

@dataclass
class PrintStmt(Stmt):
    expr: Optional[Expr] = None

@dataclass
class ExprStmt(Stmt):
    expr: Optional[Expr] = None

@dataclass
class BlockStmt(Stmt):
    stmts: List[Stmt] = None

    def __post_init__(self):
        if self.stmts is None:
            self.stmts = []

@dataclass
class FuncDef(ASTNode):
    name: str = ""
    params: List[Param] = None
    body: List[Stmt] = None

    def __post_init__(self):
        if self.params is None:
            self.params = []
        if self.body is None:
            self.body = []

@dataclass
class Program(ASTNode):
    global_arrays: List[GlobalArray] = None
    functions: List[FuncDef] = None

    def __post_init__(self):
        if self.global_arrays is None:
            self.global_arrays = []
        if self.functions is None:
            self.functions = []

@dataclass
class IntLit(Expr):
    val: int = 0

@dataclass
class VarExpr(Expr):
    name: str = ""

@dataclass
class ArrayAccessExpr(Expr):
    name: str = ""
    index_expr: Optional[Expr] = None
    site_id: int = -1

@dataclass
class UnaryExpr(Expr):
    op: str = ""
    expr: Optional[Expr] = None

@dataclass
class BinaryExpr(Expr):
    op: str = ""
    left: Optional[Expr] = None
    right: Optional[Expr] = None

@dataclass
class CallExpr(Expr):
    name: str = ""
    args: List[Expr] = None

    def __post_init__(self):
        if self.args is None:
            self.args = []
