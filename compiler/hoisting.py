"""
ISA-Preserving Loop-Guard Hoisting Transformation for MiniL (Modes H and FH).
Transforms innermost loops of the form:
  while (i < E) { ...; i = i + c }
or <=, c >= 1, into:
  if (guard) {
      // fast loop: guarded sites have checks omitted
  } else {
      // slow loop: original checked loop
  }
"""
import copy
from typing import Dict, List, Optional, Set, Tuple
from compiler.ast_nodes import (
    Program, GlobalArray, FuncDef, Param, Stmt, Expr,
    VarDeclStmt, AssignStmt, ArrayAssignStmt, IfStmt, WhileStmt,
    ReturnStmt, PrintStmt, ExprStmt, BlockStmt,
    IntLit, VarExpr, ArrayAccessExpr, UnaryExpr, BinaryExpr, CallExpr
)
from compiler.sema import Sema
from compiler.analysis import IntervalAnalysis

class HoistingResult:
    def __init__(self, transformed_ast: Program, safe_sites: Set[int], hoisted_sites: Set[int], site_mappings: Dict[int, int]):
        self.transformed_ast = transformed_ast
        self.safe_sites = safe_sites
        self.hoisted_sites = hoisted_sites
        # maps new_fast_site_id -> original_site_id (for diagnostic/tracking)
        self.site_mappings = site_mappings

class HoistingPlanner:
    def __init__(self, sema: Sema, next_site_id_start: int = 10000):
        self.sema = sema
        self.next_site_id = next_site_id_start
        self.hoisted_sites: Set[int] = set()
        self.site_mappings: Dict[int, int] = {}

    def _alloc_site_id(self, original_id: int) -> int:
        sid = self.next_site_id
        self.next_site_id += 1
        self.site_mappings[sid] = original_id
        return sid

    def plan_and_transform(self, program: Program, initial_safe_sites: Set[int]) -> HoistingResult:
        new_program = copy.deepcopy(program)
        all_safe_sites = set(initial_safe_sites)
        self.hoisted_sites.clear()
        self.site_mappings.clear()

        for func in new_program.functions:
            func.body = self._transform_stmts(func.body, all_safe_sites)

        return HoistingResult(
            transformed_ast=new_program,
            safe_sites=all_safe_sites,
            hoisted_sites=self.hoisted_sites,
            site_mappings=self.site_mappings
        )

    def _transform_stmts(self, stmts: List[Stmt], safe_sites: Set[int]) -> List[Stmt]:
        new_stmts = []
        for s in stmts:
            new_s = self._transform_stmt(s, safe_sites)
            new_stmts.append(new_s)
        return new_stmts

    def _transform_stmt(self, stmt: Stmt, safe_sites: Set[int]) -> Stmt:
        if isinstance(stmt, BlockStmt):
            stmt.stmts = self._transform_stmts(stmt.stmts, safe_sites)
            return stmt

        if isinstance(stmt, IfStmt):
            stmt.then_branch = self._transform_stmt(stmt.then_branch, safe_sites)
            if stmt.else_branch:
                stmt.else_branch = self._transform_stmt(stmt.else_branch, safe_sites)
            return stmt

        if isinstance(stmt, WhileStmt):
            # Check if this loop is innermost
            if not self._is_innermost(stmt.body):
                stmt.body = self._transform_stmt(stmt.body, safe_sites)
                return stmt

            # Check if loop satisfies hoisting conditions
            candidate_info = self._analyze_candidate_loop(stmt, safe_sites)
            if candidate_info is None:
                # Not a hoisting candidate
                stmt.body = self._transform_stmt(stmt.body, safe_sites)
                return stmt

            # Hoisting is applicable!
            guard_expr, candidate_sites = candidate_info

            # Create fast loop copy where candidate sites are allocated new site_ids and added to safe_sites
            fast_loop = copy.deepcopy(stmt)
            for site_node, orig_id in self._find_sites_in_stmt(fast_loop.body):
                if orig_id in candidate_sites:
                    new_id = self._alloc_site_id(orig_id)
                    site_node.site_id = new_id
                    safe_sites.add(new_id)
                    self.hoisted_sites.add(orig_id)

            # Original loop acts as fallback slow loop
            slow_loop = stmt

            # Return IfStmt(guard, fast_loop, slow_loop)
            return IfStmt(
                line=stmt.line,
                col=stmt.col,
                cond=guard_expr,
                then_branch=fast_loop,
                else_branch=slow_loop
            )

        return stmt

    def _is_innermost(self, body: Stmt) -> bool:
        if isinstance(body, WhileStmt):
            return False
        if isinstance(body, BlockStmt):
            for s in body.stmts:
                if not self._is_innermost(s):
                    return False
        if isinstance(body, IfStmt):
            if not self._is_innermost(body.then_branch):
                return False
            if body.else_branch and not self._is_innermost(body.else_branch):
                return False
        return True

    def _collect_assigned_vars(self, stmt: Stmt) -> Set[str]:
        assigned = set()
        if isinstance(stmt, AssignStmt):
            assigned.add(stmt.name)
        elif isinstance(stmt, VarDeclStmt):
            assigned.add(stmt.name)
        elif isinstance(stmt, BlockStmt):
            for s in stmt.stmts:
                assigned.update(self._collect_assigned_vars(s))
        elif isinstance(stmt, IfStmt):
            assigned.update(self._collect_assigned_vars(stmt.then_branch))
            if stmt.else_branch:
                assigned.update(self._collect_assigned_vars(stmt.else_branch))
        return assigned

    def _collect_vars_in_expr(self, expr: Expr) -> Set[str]:
        vars_found = set()
        if isinstance(expr, VarExpr):
            vars_found.add(expr.name)
        elif isinstance(expr, BinaryExpr):
            vars_found.update(self._collect_vars_in_expr(expr.left))
            vars_found.update(self._collect_vars_in_expr(expr.right))
        elif isinstance(expr, UnaryExpr):
            vars_found.update(self._collect_vars_in_expr(expr.expr))
        elif isinstance(expr, ArrayAccessExpr):
            vars_found.update(self._collect_vars_in_expr(expr.index_expr))
        elif isinstance(expr, CallExpr):
            for a in expr.args:
                vars_found.update(self._collect_vars_in_expr(a))
        return vars_found

    def _is_side_effect_free(self, expr: Expr) -> bool:
        if isinstance(expr, CallExpr):
            return False
        if isinstance(expr, (IntLit, VarExpr)):
            return True
        if isinstance(expr, UnaryExpr):
            return self._is_side_effect_free(expr.expr)
        if isinstance(expr, BinaryExpr):
            return self._is_side_effect_free(expr.left) and self._is_side_effect_free(expr.right)
        if isinstance(expr, ArrayAccessExpr):
            return self._is_side_effect_free(expr.index_expr)
        return True

    def _analyze_candidate_loop(self, loop: WhileStmt, safe_sites: Set[int]) -> Optional[Tuple[Expr, Set[int]]]:
        # Condition: i < E or i <= E
        cond = loop.cond
        if not isinstance(cond, BinaryExpr) or cond.op not in ("<", "<="):
            return None
        if not isinstance(cond.left, VarExpr):
            return None

        var_i = cond.left.name
        d_val = 1 if cond.op == "<=" else 0
        expr_E = cond.right

        if not self._is_side_effect_free(expr_E):
            return None

        # Check body statements
        body_stmts = loop.body.stmts if isinstance(loop.body, BlockStmt) else [loop.body]
        if not body_stmts:
            return None

        # Last statement must be increment: i = i + c with c >= 1
        last_stmt = body_stmts[-1]
        if not isinstance(last_stmt, AssignStmt) or last_stmt.name != var_i:
            return None

        rhs = last_stmt.expr
        step_val = None
        if isinstance(rhs, BinaryExpr) and rhs.op == "+":
            if isinstance(rhs.left, VarExpr) and rhs.left.name == var_i and isinstance(rhs.right, IntLit):
                step_val = rhs.right.val
            elif isinstance(rhs.right, VarExpr) and rhs.right.name == var_i and isinstance(rhs.left, IntLit):
                step_val = rhs.left.val

        if step_val is None or step_val < 1:
            return None

        # Single assignment to i: i must not be modified in body_stmts[:-1]
        body_except_last = body_stmts[:-1]
        for s in body_except_last:
            if var_i in self._collect_assigned_vars(s):
                return None

        # Variables in E must not be assigned anywhere in body
        vars_in_E = self._collect_vars_in_expr(expr_E)
        all_assigned_in_body = set()
        for s in body_stmts:
            all_assigned_in_body.update(self._collect_assigned_vars(s))
        if any(v in all_assigned_in_body for v in vars_in_E):
            return None

        # Find unknown access sites in loop body
        site_nodes = self._find_sites_in_stmt(loop.body)
        candidate_site_ids = set()
        conjuncts: List[Expr] = []

        for site_node, orig_id in site_nodes:
            if orig_id in safe_sites:
                continue # Already proven safe

            arr_name = site_node.name
            arr_size = self.sema.global_arrays[arr_name].size
            idx_expr = site_node.index_expr

            # Match idx_expr as i + K or i - K or i
            k_expr = self._extract_k(idx_expr, var_i)
            if k_expr is None:
                continue

            if not self._is_side_effect_free(k_expr):
                continue

            # K must be loop-invariant: variables in K must not be assigned in body
            vars_in_k = self._collect_vars_in_expr(k_expr)
            if any(v in all_assigned_in_body for v in vars_in_k):
                continue

            candidate_site_ids.add(orig_id)

            # Build guard conjuncts:
            # 1. (i + K >= 0)
            idx_at_entry = self._add_exprs(VarExpr(name=var_i), k_expr)
            c1 = BinaryExpr(op=">=", left=idx_at_entry, right=IntLit(val=0))

            # 2. (E + d + K <= |a|)
            e_plus_d = expr_E if d_val == 0 else BinaryExpr(op="+", left=expr_E, right=IntLit(val=1))
            upper_bound_expr = self._add_exprs(e_plus_d, k_expr)
            c2 = BinaryExpr(op="<=", left=upper_bound_expr, right=IntLit(val=arr_size))

            conjuncts.append(c1)
            conjuncts.append(c2)

        if not candidate_site_ids:
            return None

        # Combine all conjuncts with &&
        guard = conjuncts[0]
        for c in conjuncts[1:]:
            guard = BinaryExpr(op="&&", left=guard, right=c)

        return guard, candidate_site_ids

    def _extract_k(self, idx_expr: Expr, var_i: str) -> Optional[Expr]:
        if isinstance(idx_expr, VarExpr) and idx_expr.name == var_i:
            return IntLit(val=0)
        if isinstance(idx_expr, BinaryExpr):
            if idx_expr.op == "+":
                if isinstance(idx_expr.left, VarExpr) and idx_expr.left.name == var_i:
                    return idx_expr.right
                if isinstance(idx_expr.right, VarExpr) and idx_expr.right.name == var_i:
                    return idx_expr.left
            elif idx_expr.op == "-":
                if isinstance(idx_expr.left, VarExpr) and idx_expr.left.name == var_i:
                    return UnaryExpr(op="-", expr=idx_expr.right)
        return None

    def _add_exprs(self, a: Expr, b: Expr) -> Expr:
        if isinstance(b, IntLit) and b.val == 0:
            return a
        if isinstance(a, IntLit) and a.val == 0:
            return b
        return BinaryExpr(op="+", left=a, right=b)

    def _find_sites_in_stmt(self, node) -> List[Tuple[any, int]]:
        sites = []
        if isinstance(node, BlockStmt):
            for s in node.stmts:
                sites.extend(self._find_sites_in_stmt(s))
        elif isinstance(node, IfStmt):
            sites.extend(self._find_sites_in_stmt(node.cond))
            sites.extend(self._find_sites_in_stmt(node.then_branch))
            if node.else_branch:
                sites.extend(self._find_sites_in_stmt(node.else_branch))
        elif isinstance(node, WhileStmt):
            sites.extend(self._find_sites_in_stmt(node.cond))
            sites.extend(self._find_sites_in_stmt(node.body))
        elif isinstance(node, ArrayAssignStmt):
            sites.append((node, node.site_id))
            sites.extend(self._find_sites_in_stmt(node.index_expr))
            sites.extend(self._find_sites_in_stmt(node.expr))
        elif isinstance(node, ArrayAccessExpr):
            sites.append((node, node.site_id))
            sites.extend(self._find_sites_in_stmt(node.index_expr))
        elif isinstance(node, VarDeclStmt) and node.init_expr:
            sites.extend(self._find_sites_in_stmt(node.init_expr))
        elif isinstance(node, AssignStmt):
            sites.extend(self._find_sites_in_stmt(node.expr))
        elif isinstance(node, ReturnStmt) or isinstance(node, PrintStmt) or isinstance(node, ExprStmt):
            if node.expr:
                sites.extend(self._find_sites_in_stmt(node.expr))
        elif isinstance(node, BinaryExpr):
            sites.extend(self._find_sites_in_stmt(node.left))
            sites.extend(self._find_sites_in_stmt(node.right))
        elif isinstance(node, UnaryExpr):
            sites.extend(self._find_sites_in_stmt(node.expr))
        elif isinstance(node, CallExpr):
            for a in node.args:
                sites.extend(self._find_sites_in_stmt(a))
        return sites
