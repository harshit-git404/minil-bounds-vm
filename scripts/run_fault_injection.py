#!/usr/bin/env python3
"""
Mutation-based Fault Injection and Differential Testing Suite (Task 5).
Applies mutation operators:
- loop condition < to <=
- index +1
- index -1
- index +k and -k (k in 2..8)
- wrong array-bound constant
- swapped loop variables
- missing loop-update statement
Performs differential testing across R, F, S, H, FS, FH and evaluates Mode U behavior.
"""
import copy
import glob
import json
import os
import random
import subprocess
import sys
import tempfile
from typing import List, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.sema import Sema
from compiler.analysis import IntervalAnalysis
from compiler.ast_nodes import (
    Program, GlobalArray, FuncDef, Stmt, Expr,
    VarDeclStmt, AssignStmt, ArrayAssignStmt, IfStmt, WhileStmt,
    ReturnStmt, PrintStmt, ExprStmt, BlockStmt,
    IntLit, VarExpr, ArrayAccessExpr, UnaryExpr, BinaryExpr, CallExpr
)

VM_BIN = os.path.join(REPO_ROOT, "vm", "minil-vm")
MODES = ["R", "F", "S", "H", "FS", "FH"]

class AstMutator:
    @staticmethod
    def mutate_cond_lt_to_le(prog: Program) -> List[Tuple[str, Program]]:
        mutants = []
        # Find all while loops with <
        for f_idx, func in enumerate(prog.functions):
            for s_idx, stmt in enumerate(func.body):
                if isinstance(stmt, WhileStmt) and isinstance(stmt.cond, BinaryExpr) and stmt.cond.op == "<":
                    p_copy = copy.deepcopy(prog)
                    p_copy.functions[f_idx].body[s_idx].cond.op = "<="
                    mutants.append((f"cond_lt_to_le_{func.name}_{s_idx}", p_copy))
        return mutants

    @staticmethod
    def mutate_index_offsets(prog: Program, offset: int, op_name: str) -> List[Tuple[str, Program]]:
        mutants = []
        for f_idx, func in enumerate(prog.functions):
            # Find access sites
            for s_idx, stmt in enumerate(func.body):
                # Search inside stmt
                p_copy = copy.deepcopy(prog)
                target_stmt = p_copy.functions[f_idx].body[s_idx]
                mutated = AstMutator._apply_offset_to_first_site(target_stmt, offset)
                if mutated:
                    mutants.append((f"{op_name}_{func.name}_{s_idx}", p_copy))
        return mutants

    @staticmethod
    def _apply_offset_to_first_site(node, offset: int) -> bool:
        if isinstance(node, BlockStmt):
            for s in node.stmts:
                if AstMutator._apply_offset_to_first_site(s, offset):
                    return True
        elif isinstance(node, WhileStmt):
            if AstMutator._apply_offset_to_first_site(node.body, offset):
                return True
        elif isinstance(node, IfStmt):
            if AstMutator._apply_offset_to_first_site(node.then_branch, offset):
                return True
            if node.else_branch and AstMutator._apply_offset_to_first_site(node.else_branch, offset):
                return True
        elif isinstance(node, ArrayAssignStmt):
            op = "+" if offset > 0 else "-"
            node.index_expr = BinaryExpr(op=op, left=node.index_expr, right=IntLit(val=abs(offset)))
            return True
        elif isinstance(node, ArrayAccessExpr):
            op = "+" if offset > 0 else "-"
            node.index_expr = BinaryExpr(op=op, left=node.index_expr, right=IntLit(val=abs(offset)))
            return True
        return False

    @staticmethod
    def mutate_wrong_bound(prog: Program) -> List[Tuple[str, Program]]:
        mutants = []
        for a_idx, arr in enumerate(prog.global_arrays):
            p_copy = copy.deepcopy(prog)
            # reduce bound by 20%
            new_size = max(1, int(arr.size * 0.8))
            p_copy.global_arrays[a_idx].size = new_size
            mutants.append((f"wrong_bound_{arr.name}_{new_size}", p_copy))
        return mutants

    @staticmethod
    def mutate_swapped_vars(prog: Program) -> List[Tuple[str, Program]]:
        mutants = []
        for f_idx, func in enumerate(prog.functions):
            # Only swap in expressions inside inner loops where both i and j are known local variables
            p_copy = copy.deepcopy(prog)
            swapped = False
            for stmt in p_copy.functions[f_idx].body:
                if isinstance(stmt, WhileStmt) and isinstance(stmt.body, BlockStmt):
                    for inner in stmt.body.stmts:
                        if isinstance(inner, WhileStmt) and isinstance(inner.body, BlockStmt):
                            for s in inner.body.stmts:
                                # Swap only in array index expressions
                                if AstMutator._swap_vars_in_node(s, "i", "j"):
                                    swapped = True
            if swapped:
                mutants.append((f"swapped_vars_{func.name}", p_copy))
        return mutants

    @staticmethod
    def _swap_vars_in_node(node, v1: str, v2: str) -> bool:
        if isinstance(node, VarExpr):
            if node.name == v1:
                node.name = v2
                return True
            elif node.name == v2:
                node.name = v1
                return True
        elif isinstance(node, BinaryExpr):
            s1 = AstMutator._swap_vars_in_node(node.left, v1, v2)
            s2 = AstMutator._swap_vars_in_node(node.right, v1, v2)
            return s1 or s2
        elif isinstance(node, ArrayAccessExpr):
            return AstMutator._swap_vars_in_node(node.index_expr, v1, v2)
        elif isinstance(node, ArrayAssignStmt):
            s1 = AstMutator._swap_vars_in_node(node.index_expr, v1, v2)
            s2 = AstMutator._swap_vars_in_node(node.expr, v1, v2)
            return s1 or s2
        return False

    @staticmethod
    def mutate_missing_update(prog: Program) -> List[Tuple[str, Program]]:
        mutants = []
        for f_idx, func in enumerate(prog.functions):
            for s_idx, stmt in enumerate(func.body):
                if isinstance(stmt, WhileStmt) and isinstance(stmt.body, BlockStmt) and len(stmt.body.stmts) > 1:
                    # Remove last statement (increment)
                    p_copy = copy.deepcopy(prog)
                    p_copy.functions[f_idx].body[s_idx].body.stmts.pop()
                    mutants.append((f"missing_update_{func.name}_{s_idx}", p_copy))
        return mutants

def run_differential_test(ast: Program, sema: Sema) -> dict:
    results = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        for mode in MODES:
            mbc_file = os.path.join(tmpdir, f"prog_{mode}.mbc")
            from compiler.codegen import CodeGenerator
            from compiler.analysis import IntervalAnalysis
            from compiler.hoisting import HoistingPlanner

            ana = IntervalAnalysis(sema)
            ana.analyze(ast)
            safe = ana.get_safe_sites()
            target_ast = ast

            if mode in ("H", "FH"):
                planner = HoistingPlanner(sema)
                h_res = planner.plan_and_transform(ast, safe)
                target_ast = h_res.transformed_ast
                safe = h_res.safe_sites

            cg = CodeGenerator(sema, mode=mode, safe_sites=safe)
            cg.generate(target_ast)
            cg.write_bytecode(mbc_file)

            try:
                proc = subprocess.run([VM_BIN, mbc_file], capture_output=True, text=True, timeout=1.5)
                # Parse trap site if trapped
                trap_site = None
                trap_arr = None
                if proc.returncode == 2:
                    for l in proc.stderr.splitlines():
                        if "TRAP: bounds check failed" in l:
                            if "for array '" in l:
                                trap_arr = l.split("for array '")[1].split("'")[0]
                            if "site " in l:
                                trap_site = l.split("site ")[1].split()[0].rstrip("(")
                results[mode] = {
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout.strip(),
                    "trap_arr": trap_arr,
                    "trap_site": trap_site,
                    "timeout": False
                }
            except subprocess.TimeoutExpired:
                results[mode] = {"exit_code": -1, "stdout": "", "trap_arr": None, "trap_site": None, "timeout": True}

        # Also run Mode U
        mbc_u = os.path.join(tmpdir, "prog_U.mbc")
        cg_u = CodeGenerator(sema, mode="U")
        cg_u.generate(ast)
        cg_u.write_bytecode(mbc_u)
        try:
            proc_u = subprocess.run([VM_BIN, mbc_u], capture_output=True, text=True, timeout=1.5)
            results["U"] = {
                "exit_code": proc_u.returncode,
                "stdout": proc_u.stdout.strip(),
                "timeout": False
            }
        except subprocess.TimeoutExpired:
            results["U"] = {"exit_code": -1, "stdout": "", "timeout": True}

    return results

def run_fault_injection():
    print("\nStarting Fault Injection Study (Task 5)...")
    os.makedirs("results", exist_ok=True)
    rng = random.Random(1337)

    benchmarks = sorted(glob.glob("benchmarks/*.minil"))
    # Exclude fib (null control, no arrays)
    benchmarks = [b for b in benchmarks if "fib" not in b]

    records = []
    total_mutants = 0
    faulty_mutants = 0
    benign_mutants = 0

    operator_stats = {}

    for b_path in benchmarks:
        b_name = os.path.splitext(os.path.basename(b_path))[0]
        with open(b_path, "r") as f:
            orig_code = f.read()

        orig_ast = Parser(Lexer(orig_code).tokenize()).parse()
        orig_sema = Sema()
        orig_sema.analyze(orig_ast)
        orig_ana = IntervalAnalysis(orig_sema)
        orig_rep = orig_ana.analyze(orig_ast)

        orig_non_proved = orig_rep["summary"]["unknown"] + orig_rep["summary"]["violation"]

        # Run unmutated program to get baseline stdout
        diff_orig = run_differential_test(orig_ast, orig_sema)
        orig_stdout = diff_orig["R"]["stdout"]

        # Generate candidates for each operator
        candidate_mutants = []

        # 1. cond_lt_to_le
        for name, m_ast in AstMutator.mutate_cond_lt_to_le(orig_ast):
            candidate_mutants.append(("cond_lt_to_le", name, m_ast))

        # 2. index_plus_1
        for name, m_ast in AstMutator.mutate_index_offsets(orig_ast, 1, "index_plus_1"):
            candidate_mutants.append(("index_plus_1", name, m_ast))

        # 3. index_minus_1
        for name, m_ast in AstMutator.mutate_index_offsets(orig_ast, -1, "index_minus_1"):
            candidate_mutants.append(("index_minus_1", name, m_ast))

        # 4. index_plus_k (k in 2..8)
        k_plus = rng.randint(2, 8)
        for name, m_ast in AstMutator.mutate_index_offsets(orig_ast, k_plus, f"index_plus_{k_plus}"):
            candidate_mutants.append(("index_plus_k", name, m_ast))

        # 5. index_minus_k (k in 2..8)
        k_minus = rng.randint(2, 8)
        for name, m_ast in AstMutator.mutate_index_offsets(orig_ast, -k_minus, f"index_minus_{k_minus}"):
            candidate_mutants.append(("index_minus_k", name, m_ast))

        # 6. wrong_array_bound
        for name, m_ast in AstMutator.mutate_wrong_bound(orig_ast):
            candidate_mutants.append(("wrong_array_bound", name, m_ast))

        # 7. swapped_loop_vars
        for name, m_ast in AstMutator.mutate_swapped_vars(orig_ast):
            candidate_mutants.append(("swapped_loop_vars", name, m_ast))

        # 8. missing_loop_update
        for name, m_ast in AstMutator.mutate_missing_update(orig_ast):
            candidate_mutants.append(("missing_loop_update", name, m_ast))

        # Group by operator and sample up to 5 per operator
        by_op = {}
        for op, m_id, m_ast in candidate_mutants:
            by_op.setdefault(op, []).append((m_id, m_ast))

        sampled = []
        for op, m_list in by_op.items():
            sample_count = min(5, len(m_list))
            for m_id, m_ast in rng.sample(m_list, sample_count):
                sampled.append((op, m_id, m_ast))

        # Evaluate each sampled mutant
        for op, m_id, m_ast in sampled:
            # 1. Semantic and Interval Analysis
            m_sema = Sema()
            try:
                m_sema.analyze(m_ast)
            except Exception:
                continue

            total_mutants += 1
            if op not in operator_stats:
                operator_stats[op] = {
                    "total": 0, "faulty": 0, "benign": 0,
                    "definite_violations": 0, "new_alarms": 0, "neither": 0,
                    "u_silent_corrupt": 0, "u_crash": 0, "u_same_output": 0
                }
            op_st = operator_stats[op]
            op_st["total"] += 1

            m_ana = IntervalAnalysis(m_sema)
            m_rep = m_ana.analyze(m_ast)

            m_definite_violation = (m_rep["summary"]["violation"] > 0)
            m_non_proved = m_rep["summary"]["unknown"] + m_rep["summary"]["violation"]
            m_more_alarms = (m_non_proved > orig_non_proved)

            static_category = "neither"
            if m_definite_violation:
                static_category = "definite_violation"
                op_st["definite_violations"] += 1
            elif m_more_alarms:
                static_category = "new_alarm"
                op_st["new_alarms"] += 1
            else:
                op_st["neither"] += 1

            # 2. Differential Execution
            diff_res = run_differential_test(m_ast, m_sema)

            # Check if mutant is faulty (Mode R traps)
            is_faulty = (diff_res["R"]["exit_code"] == 2)
            if is_faulty:
                faulty_mutants += 1
                op_st["faulty"] += 1
            else:
                benign_mutants += 1
                op_st["benign"] += 1

            # Verify differential consistency across checked modes: R, F, S, H, FS, FH
            # exit_code, trap_arr, trap_site must match
            r_info = diff_res["R"]
            diff_match = True
            for m in ("F", "S", "H", "FS", "FH"):
                m_info = diff_res[m]
                if m_info["exit_code"] != r_info["exit_code"]:
                    diff_match = False
                if is_faulty and m_info["trap_arr"] != r_info["trap_arr"]:
                    diff_match = False

            # Check Mode U behavior
            u_info = diff_res["U"]
            u_behavior = "silent_same"
            if u_info["exit_code"] != 0:
                u_behavior = "crash"
                op_st["u_crash"] += 1
            elif u_info["stdout"] != orig_stdout:
                u_behavior = "silent_corrupt"
                op_st["u_silent_corrupt"] += 1
            else:
                u_behavior = "silent_same"
                op_st["u_same_output"] += 1

            records.append({
                "benchmark": b_name,
                "operator": op,
                "mutant_id": m_id,
                "classification": "faulty" if is_faulty else "benign",
                "static_finding": static_category,
                "diff_match": diff_match,
                "u_behavior": u_behavior,
                "trap_array": r_info.get("trap_arr"),
                "trap_site": r_info.get("trap_site")
            })

    # Output CSV
    csv_path = "results/fault_injection_results.csv"
    with open(csv_path, "w") as f:
        f.write("benchmark,operator,mutant_id,classification,static_finding,diff_match,u_behavior,trap_array,trap_site\n")
        for r in records:
            f.write(f"{r['benchmark']},{r['operator']},{r['mutant_id']},{r['classification']},{r['static_finding']},{r['diff_match']},{r['u_behavior']},{r['trap_array']},{r['trap_site']}\n")

    summary_data = {
        "total_mutants": total_mutants,
        "faulty_mutants": faulty_mutants,
        "benign_mutants": benign_mutants,
        "operator_stats": operator_stats
    }
    with open("results/fault_injection_summary.json", "w") as f:
        json.dump(summary_data, f, indent=2)

    print(f"\nFault Injection Complete: {total_mutants} mutants tested ({faulty_mutants} faulty, {benign_mutants} benign).")
    print(f"Results written to {csv_path} and results/fault_injection_summary.json")

if __name__ == "__main__":
    run_fault_injection()
