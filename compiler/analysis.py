"""
Interval Abstract Interpretation and Array Bounds Safety Analysis for MiniL.
Implements:
- Non-relational interval domain with +-inf and bottom.
- Transfer functions for arithmetic, division (truncating), modulo (C99 style).
- Condition refinement for relations (x + k <|> e and symmetric).
- Kleene loop iteration with widening after 2 iterations and 2 narrowing steps.
- Per-site index interval collection and classification (safe, violation, unknown).
- Assumption: 64-bit signed arithmetic does not wrap around.
"""
import copy
import json
import math
from typing import Dict, List, Optional, Set, Tuple
from compiler.ast_nodes import (
    Program, GlobalArray, FuncDef, Param, Stmt, Expr,
    VarDeclStmt, AssignStmt, ArrayAssignStmt, IfStmt, WhileStmt,
    ReturnStmt, PrintStmt, ExprStmt, BlockStmt,
    IntLit, VarExpr, ArrayAccessExpr, UnaryExpr, BinaryExpr, CallExpr
)
from compiler.sema import Sema

INF = float("inf")

class Interval:
    def __init__(self, low: float, high: float):
        self.low = low
        self.high = high

    @classmethod
    def bot(cls):
        return cls(INF, -INF)

    @classmethod
    def top(cls):
        return cls(-INF, INF)

    @classmethod
    def const(cls, val: int):
        return cls(float(val), float(val))

    def is_bot(self) -> bool:
        return self.low > self.high

    def is_top(self) -> bool:
        return self.low == -INF and self.high == INF

    def __repr__(self):
        if self.is_bot():
            return "⊥"
        l_str = "-inf" if self.low == -INF else str(int(self.low))
        h_str = "+inf" if self.high == INF else str(int(self.high))
        return f"[{l_str}, {h_str}]"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Interval):
            return False
        if self.is_bot() and other.is_bot():
            return True
        return self.low == other.low and self.high == other.high

    def is_subset(self, other: "Interval") -> bool:
        if self.is_bot():
            return True
        if other.is_bot():
            return False
        return self.low >= other.low and self.high <= other.high

    def join(self, other: "Interval") -> "Interval":
        if self.is_bot():
            return Interval(other.low, other.high)
        if other.is_bot():
            return Interval(self.low, self.high)
        return Interval(min(self.low, other.low), max(self.high, other.high))

    def meet(self, other: "Interval") -> "Interval":
        if self.is_bot() or other.is_bot():
            return Interval.bot()
        low = max(self.low, other.low)
        high = min(self.high, other.high)
        if low > high:
            return Interval.bot()
        return Interval(low, high)

    def widen(self, other: "Interval") -> "Interval":
        if self.is_bot():
            return Interval(other.low, other.high)
        if other.is_bot():
            return Interval(self.low, self.high)
        low = self.low if other.low >= self.low else -INF
        high = self.high if other.high <= self.high else INF
        return Interval(low, high)

    def narrow(self, other: "Interval") -> "Interval":
        if self.is_bot() or other.is_bot():
            return Interval.bot()
        low = other.low if self.low == -INF else self.low
        high = other.high if self.high == INF else self.high
        if low > high:
            return Interval.bot()
        return Interval(low, high)

    def add(self, other: "Interval") -> "Interval":
        if self.is_bot() or other.is_bot():
            return Interval.bot()
        return Interval(self.low + other.low, self.high + other.high)

    def sub(self, other: "Interval") -> "Interval":
        if self.is_bot() or other.is_bot():
            return Interval.bot()
        return Interval(self.low - other.high, self.high - other.low)

    def neg(self) -> "Interval":
        if self.is_bot():
            return Interval.bot()
        return Interval(-self.high, -self.low)

    def mul(self, other: "Interval") -> "Interval":
        if self.is_bot() or other.is_bot():
            return Interval.bot()
        if (self.low == 0 and self.high == 0) or (other.low == 0 and other.high == 0):
            return Interval.const(0)
        
        candidates = []
        for x in (self.low, self.high):
            for y in (other.low, other.high):
                if x == 0 or y == 0:
                    candidates.append(0.0)
                elif x in (-INF, INF) or y in (-INF, INF):
                    # Handle inf multiplication signs
                    sign = (1 if x > 0 else -1) * (1 if y > 0 else -1)
                    candidates.append(INF if sign > 0 else -INF)
                else:
                    candidates.append(x * y)
        return Interval(min(candidates), max(candidates))

    def div(self, other: "Interval") -> "Interval":
        if self.is_bot() or other.is_bot():
            return Interval.bot()
        # Truncating integer division toward zero
        # If other is strictly 0:
        if other.low == 0 and other.high == 0:
            return Interval.bot()

        # Non-zero subintervals of other
        parts = []
        if other.low < 0:
            parts.append(Interval(other.low, min(-1.0, other.high)))
        if other.high > 0:
            parts.append(Interval(max(1.0, other.low), other.high))

        results = []
        for d in parts:
            endpoints = []
            for x in (self.low, self.high):
                for y in (d.low, d.high):
                    if x in (-INF, INF):
                        sign = (1 if x > 0 else -1) * (1 if y > 0 else -1)
                        endpoints.append(INF if sign > 0 else -INF)
                    else:
                        endpoints.append(float(int(x / y)))
            results.append(Interval(min(endpoints), max(endpoints)))

        if not results:
            return Interval.bot()
        res = results[0]
        for r in results[1:]:
            res = res.join(r)
        return res

    def mod(self, other: "Interval") -> "Interval":
        if self.is_bot() or other.is_bot():
            return Interval.bot()
        if other.low == 0 and other.high == 0:
            return Interval.bot()

        # C-style remainder: sign matches dividend (self).
        # Max magnitude of remainder is |other| - 1
        max_d = max(abs(other.low), abs(other.high))
        if max_d == INF or max_d <= 1:
            # unbounded or modulo 1 (always 0)
            if max_d <= 1:
                return Interval.const(0)
            bound = INF
        else:
            bound = max_d - 1

        low = -bound if self.low < 0 else 0.0
        high = bound if self.high > 0 else 0.0

        # If dividend itself is more tightly bounded, clamp it
        if self.low != -INF:
            low = max(low, self.low)
        if self.high != INF:
            high = min(high, self.high)

        if low > high:
            return Interval.const(0)
        return Interval(low, high)

class Env:
    def __init__(self, mapping: Optional[Dict[str, Interval]] = None):
        self.mapping: Dict[str, Interval] = copy.deepcopy(mapping) if mapping else {}

    def get(self, var: str) -> Interval:
        return self.mapping.get(var, Interval.top())

    def set(self, var: str, interval: Interval):
        self.mapping[var] = interval

    def is_bot(self) -> bool:
        return any(i.is_bot() for i in self.mapping.values())

    def copy(self) -> "Env":
        return Env(self.mapping)

    def join(self, other: "Env") -> "Env":
        if self.is_bot():
            return other.copy()
        if other.is_bot():
            return self.copy()
        new_map = {}
        all_keys = set(self.mapping.keys()).union(other.mapping.keys())
        for k in all_keys:
            new_map[k] = self.get(k).join(other.get(k))
        return Env(new_map)

    def widen(self, other: "Env") -> "Env":
        if self.is_bot():
            return other.copy()
        if other.is_bot():
            return self.copy()
        new_map = {}
        all_keys = set(self.mapping.keys()).union(other.mapping.keys())
        for k in all_keys:
            new_map[k] = self.get(k).widen(other.get(k))
        return Env(new_map)

    def narrow(self, other: "Env") -> "Env":
        if self.is_bot() or other.is_bot():
            return Env()
        new_map = {}
        all_keys = set(self.mapping.keys()).union(other.mapping.keys())
        for k in all_keys:
            new_map[k] = self.get(k).narrow(other.get(k))
        return Env(new_map)

    def is_subset(self, other: "Env") -> bool:
        if self.is_bot():
            return True
        if other.is_bot():
            return False
        for k in self.mapping:
            if not self.get(k).is_subset(other.get(k)):
                return False
        return True

    def __eq__(self, other) -> bool:
        if not isinstance(other, Env):
            return False
        all_keys = set(self.mapping.keys()).union(other.mapping.keys())
        return all(self.get(k) == other.get(k) for k in all_keys)

class SiteInfo:
    def __init__(self, site_id: int, array_name: str, array_size: int, line: int, col: int):
        self.site_id = site_id
        self.array_name = array_name
        self.array_size = array_size
        self.line = line
        self.col = col
        self.interval = Interval.bot()
        self.classification = "unknown" # safe, violation, unknown

    def record_index(self, interval: Interval):
        self.interval = self.interval.join(interval)

    def finalize(self):
        if self.interval.is_bot():
            self.classification = "safe" # unreachable site
            return

        # Check safe: interval is subset of [0, array_size - 1]
        bound_low = 0.0
        bound_high = float(self.array_size - 1)

        if self.interval.low >= bound_low and self.interval.high <= bound_high:
            self.classification = "safe"
        elif self.interval.high < bound_low or self.interval.low > bound_high:
            self.classification = "violation"
        else:
            self.classification = "unknown"

    def to_dict(self):
        l_val = None if self.interval.low == -INF else (int(self.interval.low) if not self.interval.is_bot() else None)
        h_val = None if self.interval.high == INF else (int(self.interval.high) if not self.interval.is_bot() else None)
        return {
            "site_id": self.site_id,
            "array": self.array_name,
            "array_size": self.array_size,
            "line": self.line,
            "col": self.col,
            "interval": [l_val, h_val],
            "interval_str": str(self.interval),
            "classification": self.classification
        }

class IntervalAnalysis:
    def __init__(self, sema: Sema):
        self.sema = sema
        self.sites: Dict[int, SiteInfo] = {}

    def analyze(self, program: Program) -> Dict[str, any]:
        # Initialize sites from global arrays
        self.sites.clear()
        self._collect_sites(program)

        # Analyze each function independently (parameters are top)
        for func in program.functions:
            func_sym = self.sema.functions[func.name]
            init_env = Env()
            # Parameters start at TOP
            for p in func.params:
                init_env.set(p.name, Interval.top())
            # Locals start at 0
            for name, slot in func_sym.slots.items():
                if name not in [p.name for p in func.params]:
                    init_env.set(name, Interval.const(0))

            # Run analysis and record site intervals
            self._analyze_stmts(func.body, init_env, record=True)

        # Finalize classification for each site
        safe_count = 0
        violation_count = 0
        unknown_count = 0

        for site in self.sites.values():
            site.finalize()
            if site.classification == "safe":
                safe_count += 1
            elif site.classification == "violation":
                violation_count += 1
            else:
                unknown_count += 1

        report = {
            "summary": {
                "total_sites": len(self.sites),
                "safe": safe_count,
                "violation": violation_count,
                "unknown": unknown_count
            },
            "sites": [s.to_dict() for s in sorted(self.sites.values(), key=lambda x: x.site_id)]
        }
        return report

    def get_safe_sites(self) -> Set[int]:
        return {s.site_id for s in self.sites.values() if s.classification == "safe"}

    def _collect_sites(self, node):
        if isinstance(node, Program):
            for f in node.functions:
                self._collect_sites(f)
        elif isinstance(node, FuncDef):
            for s in node.body:
                self._collect_sites(s)
        elif isinstance(node, BlockStmt):
            for s in node.stmts:
                self._collect_sites(s)
        elif isinstance(node, IfStmt):
            self._collect_sites(node.cond)
            self._collect_sites(node.then_branch)
            if node.else_branch:
                self._collect_sites(node.else_branch)
        elif isinstance(node, WhileStmt):
            self._collect_sites(node.cond)
            self._collect_sites(node.body)
        elif isinstance(node, VarDeclStmt):
            if node.init_expr:
                self._collect_sites(node.init_expr)
        elif isinstance(node, AssignStmt):
            self._collect_sites(node.expr)
        elif isinstance(node, ArrayAssignStmt):
            arr = self.sema.global_arrays[node.name]
            self.sites[node.site_id] = SiteInfo(node.site_id, node.name, arr.size, node.line, node.col)
            self._collect_sites(node.index_expr)
            self._collect_sites(node.expr)
        elif isinstance(node, ArrayAccessExpr):
            arr = self.sema.global_arrays[node.name]
            self.sites[node.site_id] = SiteInfo(node.site_id, node.name, arr.size, node.line, node.col)
            self._collect_sites(node.index_expr)
        elif isinstance(node, ReturnStmt) or isinstance(node, PrintStmt) or isinstance(node, ExprStmt):
            if node.expr:
                self._collect_sites(node.expr)
        elif isinstance(node, BinaryExpr):
            self._collect_sites(node.left)
            self._collect_sites(node.right)
        elif isinstance(node, UnaryExpr):
            self._collect_sites(node.expr)
        elif isinstance(node, CallExpr):
            for a in node.args:
                self._collect_sites(a)

    def _analyze_stmts(self, stmts: List[Stmt], env: Env, record: bool) -> Env:
        curr_env = env
        for s in stmts:
            if curr_env.is_bot():
                break
            curr_env = self._analyze_stmt(s, curr_env, record)
        return curr_env

    def _analyze_stmt(self, stmt: Stmt, env: Env, record: bool) -> Env:
        if env.is_bot():
            return env

        if isinstance(stmt, VarDeclStmt):
            val_int = self._eval_expr(stmt.init_expr, env, record) if stmt.init_expr else Interval.const(0)
            new_env = env.copy()
            new_env.set(stmt.name, val_int)
            return new_env

        elif isinstance(stmt, AssignStmt):
            val_int = self._eval_expr(stmt.expr, env, record)
            new_env = env.copy()
            new_env.set(stmt.name, val_int)
            return new_env

        elif isinstance(stmt, ArrayAssignStmt):
            idx_int = self._eval_expr(stmt.index_expr, env, record)
            if record and stmt.site_id in self.sites:
                self.sites[stmt.site_id].record_index(idx_int)
            self._eval_expr(stmt.expr, env, record)
            return env

        elif isinstance(stmt, IfStmt):
            then_env = self._refine_cond(stmt.cond, env, is_true=True)
            else_env = self._refine_cond(stmt.cond, env, is_true=False)

            out_then = self._analyze_stmt(stmt.then_branch, then_env, record) if stmt.then_branch else then_env
            out_else = self._analyze_stmt(stmt.else_branch, else_env, record) if stmt.else_branch else else_env
            return out_then.join(out_else)

        elif isinstance(stmt, WhileStmt):
            # Kleene iteration: 2 iterations, then widening, then 2 narrowing steps
            head_env = env.copy()
            stabilized = False
            for it in range(2):
                body_in = self._refine_cond(stmt.cond, head_env, is_true=True)
                body_out = self._analyze_stmt(stmt.body, body_in, record=False)
                next_head = env.join(body_out)
                if next_head.is_subset(head_env):
                    head_env = next_head
                    stabilized = True
                    break
                head_env = next_head

            if not stabilized:
                # Widening phase until stabilization
                for _ in range(20):
                    body_in = self._refine_cond(stmt.cond, head_env, is_true=True)
                    body_out = self._analyze_stmt(stmt.body, body_in, record=False)
                    next_head = env.join(body_out)
                    if next_head.is_subset(head_env):
                        break
                    widened = head_env.widen(next_head)
                    if widened == head_env:
                        break
                    head_env = widened

            # Two narrowing steps
            for _ in range(2):
                body_in = self._refine_cond(stmt.cond, head_env, is_true=True)
                body_out = self._analyze_stmt(stmt.body, body_in, record=False)
                narrowed = head_env.narrow(env.join(body_out))
                if narrowed == head_env:
                    break
                head_env = narrowed

            # Final recording pass through the loop body if record=True
            if record:
                body_in = self._refine_cond(stmt.cond, head_env, is_true=True)
                self._analyze_stmt(stmt.body, body_in, record=True)

            # Exit environment
            return self._refine_cond(stmt.cond, head_env, is_true=False)

        elif isinstance(stmt, ReturnStmt):
            self._eval_expr(stmt.expr, env, record)
            return env

        elif isinstance(stmt, PrintStmt):
            self._eval_expr(stmt.expr, env, record)
            return env

        elif isinstance(stmt, ExprStmt):
            self._eval_expr(stmt.expr, env, record)
            return env

        elif isinstance(stmt, BlockStmt):
            return self._analyze_stmts(stmt.stmts, env, record)

        return env

    def _eval_expr(self, expr: Expr, env: Env, record: bool) -> Interval:
        if env.is_bot():
            return Interval.bot()

        if isinstance(expr, IntLit):
            return Interval.const(expr.val)

        elif isinstance(expr, VarExpr):
            return env.get(expr.name)

        elif isinstance(expr, ArrayAccessExpr):
            idx_int = self._eval_expr(expr.index_expr, env, record)
            if record and expr.site_id in self.sites:
                self.sites[expr.site_id].record_index(idx_int)
            # Array-loaded values are TOP in non-relational interval domain
            return Interval.top()

        elif isinstance(expr, UnaryExpr):
            sub = self._eval_expr(expr.expr, env, record)
            if expr.op == "-":
                return sub.neg()
            elif expr.op == "!":
                if sub.is_bot(): return Interval.bot()
                if sub.low == 0 and sub.high == 0:
                    return Interval.const(1)
                elif sub.low > 0 or sub.high < 0:
                    return Interval.const(0)
                else:
                    return Interval(0.0, 1.0)
            return sub

        elif isinstance(expr, BinaryExpr):
            l = self._eval_expr(expr.left, env, record)
            r = self._eval_expr(expr.right, env, record)

            if expr.op == "+": return l.add(r)
            if expr.op == "-": return l.sub(r)
            if expr.op == "*": return l.mul(r)
            if expr.op == "/": return l.div(r)
            if expr.op == "%": return l.mod(r)

            # Comparisons evaluate to [0, 1]
            if expr.op in ("==", "!=", "<", "<=", ">", ">="):
                if l.is_bot() or r.is_bot():
                    return Interval.bot()
                # If definitely true or definitely false
                if expr.op == "<":
                    if l.high < r.low: return Interval.const(1)
                    if l.low >= r.high: return Interval.const(0)
                elif expr.op == "<=":
                    if l.high <= r.low: return Interval.const(1)
                    if l.low > r.high: return Interval.const(0)
                elif expr.op == ">":
                    if l.low > r.high: return Interval.const(1)
                    if l.high <= r.low: return Interval.const(0)
                elif expr.op == ">=":
                    if l.low >= r.high: return Interval.const(1)
                    if l.high < r.low: return Interval.const(0)
                elif expr.op == "==":
                    if l.low == l.high == r.low == r.high: return Interval.const(1)
                    if l.high < r.low or l.low > r.high: return Interval.const(0)
                elif expr.op == "!=":
                    if l.high < r.low or l.low > r.high: return Interval.const(1)
                    if l.low == l.high == r.low == r.high: return Interval.const(0)
                return Interval(0.0, 1.0)

            if expr.op in ("&&", "||"):
                return Interval(0.0, 1.0)

        elif isinstance(expr, CallExpr):
            for a in expr.args:
                self._eval_expr(a, env, record)
            # Function calls return TOP in intraprocedural analysis
            return Interval.top()

        return Interval.top()

    def _decompose_affine(self, expr: Expr) -> Tuple[Optional[str], int]:
        """Recognizes forms: x, x + k, x - k, k + x where k is constant integer."""
        if isinstance(expr, VarExpr):
            return (expr.name, 0)
        if isinstance(expr, BinaryExpr):
            if expr.op == "+":
                if isinstance(expr.left, VarExpr) and isinstance(expr.right, IntLit):
                    return (expr.left.name, expr.right.val)
                if isinstance(expr.left, IntLit) and isinstance(expr.right, VarExpr):
                    return (expr.right.name, expr.left.val)
            elif expr.op == "-":
                if isinstance(expr.left, VarExpr) and isinstance(expr.right, IntLit):
                    return (expr.left.name, -expr.right.val)
        return (None, 0)

    def _refine_cond(self, cond: Expr, env: Env, is_true: bool) -> Env:
        if env.is_bot():
            return env

        if isinstance(cond, UnaryExpr) and cond.op == "!":
            return self._refine_cond(cond.expr, env, is_true=not is_true)

        if isinstance(cond, BinaryExpr):
            op = cond.op

            # Logical conjunction / disjunction
            if op == "&&":
                if is_true:
                    env1 = self._refine_cond(cond.left, env, True)
                    return self._refine_cond(cond.right, env1, True)
                else:
                    env_left_false = self._refine_cond(cond.left, env, False)
                    env_right_false = self._refine_cond(cond.right, env, False)
                    return env_left_false.join(env_right_false)

            if op == "||":
                if is_true:
                    env_left_true = self._refine_cond(cond.left, env, True)
                    env_right_true = self._refine_cond(cond.right, env, True)
                    return env_left_true.join(env_right_true)
                else:
                    env1 = self._refine_cond(cond.left, env, False)
                    return self._refine_cond(cond.right, env1, False)

            # Invert comparison operator if is_true is False
            comp_op = op
            if not is_true:
                inv_map = {
                    "<": ">=",
                    "<=": ">",
                    ">": "<=",
                    ">=": "<",
                    "==": "!=",
                    "!=": "=="
                }
                if comp_op in inv_map:
                    comp_op = inv_map[comp_op]
                else:
                    return env

            new_env = env.copy()

            # Condition refinement for x + k <|> e and e <|> y + k
            left_var, left_k = self._decompose_affine(cond.left)
            right_var, right_k = self._decompose_affine(cond.right)

            right_int = self._eval_expr(cond.right, env, record=False)
            left_int = self._eval_expr(cond.left, env, record=False)

            if left_var is not None and not right_int.is_bot():
                # x + k <|> e  => x <|> e - k
                curr_x = new_env.get(left_var)
                bound_int = None
                if comp_op == "<":
                    # x + k < e => x <= right_int.high - k - 1
                    bound_int = Interval(-INF, right_int.high - left_k - 1)
                elif comp_op == "<=":
                    bound_int = Interval(-INF, right_int.high - left_k)
                elif comp_op == ">":
                    bound_int = Interval(right_int.low - left_k + 1, INF)
                elif comp_op == ">=":
                    bound_int = Interval(right_int.low - left_k, INF)
                elif comp_op == "==":
                    bound_int = Interval(right_int.low - left_k, right_int.high - left_k)
                elif comp_op == "!=":
                    if right_int.low == right_int.high:
                        val = right_int.low - left_k
                        if curr_x.low == val:
                            bound_int = Interval(val + 1, curr_x.high)
                        elif curr_x.high == val:
                            bound_int = Interval(curr_x.low, val - 1)

                if bound_int is not None:
                    new_env.set(left_var, curr_x.meet(bound_int))

            if right_var is not None and not left_int.is_bot():
                # e <|> y + k  => y <|>inv e - k
                curr_y = new_env.get(right_var)
                bound_int = None
                if comp_op == "<":
                    # e < y + k => y + k > e => y >= left_int.low - right_k + 1
                    bound_int = Interval(left_int.low - right_k + 1, INF)
                elif comp_op == "<=":
                    bound_int = Interval(left_int.low - right_k, INF)
                elif comp_op == ">":
                    bound_int = Interval(-INF, left_int.high - right_k - 1)
                elif comp_op == ">=":
                    bound_int = Interval(-INF, left_int.high - right_k)
                elif comp_op == "==":
                    bound_int = Interval(left_int.low - right_k, left_int.high - right_k)
                elif comp_op == "!=":
                    if left_int.low == left_int.high:
                        val = left_int.low - right_k
                        if curr_y.low == val:
                            bound_int = Interval(val + 1, curr_y.high)
                        elif curr_y.high == val:
                            bound_int = Interval(curr_y.low, val - 1)

                if bound_int is not None:
                    new_env.set(right_var, curr_y.meet(bound_int))

            return new_env

        return env
