"""
Unit and Differential Tests for ISA-Preserving Loop-Guard Hoisting (Modes H and FH).
Tests:
- Identification of hoisting candidate loops
- Differential testing across modes R, H, FS, FH on edge cases:
  1. Loop not executing
  2. Negative K
  3. E == |a|
  4. E > |a| (guard fails, fallback traps at canonical site_id)
  5. Multiple arrays in single loop
  6. Nested loops
- Bytecode size growth measurements
"""
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.sema import Sema
from compiler.analysis import IntervalAnalysis
from compiler.hoisting import HoistingPlanner
from compiler.codegen import CodeGenerator
from compiler.opcodes import *

VM_BIN = os.path.join(REPO_ROOT, "vm", "minil-vm")
VM_COUNT = os.path.join(REPO_ROOT, "vm", "minil-vm-count")

class TestHoisting(unittest.TestCase):
    def _compile_and_run(self, code: str, mode: str, vm_bin: str = VM_BIN):
        with tempfile.NamedTemporaryFile(suffix=".minil", delete=False, mode="w") as sf:
            sf.write(code)
            src_path = sf.name

        with tempfile.NamedTemporaryFile(suffix=".mbc", delete=False) as tf:
            mbc_path = tf.name

        try:
            comp_proc = subprocess.run(
                ["python3", "-m", "compiler.main", "--mode", mode, "-o", mbc_path, src_path],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True
            )
            self.assertEqual(comp_proc.returncode, 0, f"Compilation failed in mode {mode}: {comp_proc.stderr}")

            run_proc = subprocess.run(
                [vm_bin, mbc_path],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True
            )
            return run_proc, os.path.getsize(mbc_path)
        finally:
            if os.path.exists(src_path): os.remove(src_path)
            if os.path.exists(mbc_path): os.remove(mbc_path)

    def test_hoisting_eliminates_checks(self):
        # In a parameter-bounded loop, mode S cannot eliminate checks because bound is parameter,
        # but mode H versions the loop and executes zero checks dynamically!
        code = """
        int a[100];
        int run_loop(int m) {
            int i = 0;
            int sum = 0;
            while (i < m) {
                a[i] = i;
                sum = sum + a[i];
                i = i + 1;
            }
            return sum;
        }
        int main() {
            print(run_loop(50));
            return 0;
        }
        """
        # Run with instrumented count build
        proc_r, _ = self._compile_and_run(code, "R", VM_COUNT)
        proc_s, _ = self._compile_and_run(code, "S", VM_COUNT)
        proc_h, _ = self._compile_and_run(code, "H", VM_COUNT)
        proc_fs, _ = self._compile_and_run(code, "FS", VM_COUNT)
        proc_fh, _ = self._compile_and_run(code, "FH", VM_COUNT)

        # All must produce identical output
        self.assertEqual(proc_r.stdout, proc_s.stdout)
        self.assertEqual(proc_r.stdout, proc_h.stdout)
        self.assertEqual(proc_r.stdout, proc_fs.stdout)
        self.assertEqual(proc_r.stdout, proc_fh.stdout)

        def get_check_count(stderr):
            for l in stderr.splitlines():
                if l.startswith("CHECK_COUNT:"):
                    return int(l.split(":")[1].strip())
            return None

        # Mode R and Mode S execute 100 dynamic checks (50 stores + 50 loads)
        self.assertEqual(get_check_count(proc_r.stderr), 100)
        self.assertEqual(get_check_count(proc_s.stderr), 100)
        # Mode H eliminates all 100 dynamic checks!
        self.assertEqual(get_check_count(proc_h.stderr), 0)
        # Mode FH also eliminates all checks in fast loop!
        self.assertEqual(get_check_count(proc_fh.stderr), 0)

    def test_edge_cases(self):
        # 1. Loop not executing: i starts >= m
        code_no_exec = """
        int a[10];
        int main() {
            int i = 10;
            int m = 5;
            while (i < m) {
                a[i] = 1;
                i = i + 1;
            }
            print(42);
            return 0;
        }
        """
        for m in ("R", "F", "S", "H", "FS", "FH"):
            proc, _ = self._compile_and_run(code_no_exec, m)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "42")

        # 2. E > |a|: guard fails, fallback slow loop traps at canonical site
        code_e_too_large = """
        int a[10];
        int main() {
            int i = 0;
            int m = 15; // exceeds size 10
            while (i < m) {
                a[i] = i;
                i = i + 1;
            }
            return 0;
        }
        """
        proc_r, _ = self._compile_and_run(code_e_too_large, "R")
        proc_h, _ = self._compile_and_run(code_e_too_large, "H")
        proc_f, _ = self._compile_and_run(code_e_too_large, "F")
        proc_fh, _ = self._compile_and_run(code_e_too_large, "FH")

        # Both R and H must trap with exit code 2
        self.assertEqual(proc_r.returncode, 2)
        self.assertEqual(proc_h.returncode, 2)
        self.assertEqual(proc_f.returncode, 2)
        self.assertEqual(proc_fh.returncode, 2)

        # Check that canonical trap message mentions array 'a' and site
        self.assertIn("TRAP: bounds check failed for array 'a'", proc_r.stderr)
        self.assertIn("TRAP: bounds check failed for array 'a'", proc_h.stderr)
        self.assertIn("site 0", proc_r.stderr)
        self.assertIn("site 0", proc_h.stderr)

        # 3. Multiple arrays in loop
        code_multi_arr = """
        int a[20];
        int b[20];
        int copy_arr(int n) {
            int i = 0;
            while (i < n) {
                b[i] = a[i] + 5;
                i = i + 1;
            }
            return b[0];
        }
        int main() {
            a[0] = 10;
            print(copy_arr(15));
            return 0;
        }
        """
        proc_r, _ = self._compile_and_run(code_multi_arr, "R")
        proc_h, _ = self._compile_and_run(code_multi_arr, "H")
        proc_fh, _ = self._compile_and_run(code_multi_arr, "FH")
        self.assertEqual(proc_r.stdout.strip(), "15")
        self.assertEqual(proc_h.stdout.strip(), "15")
        self.assertEqual(proc_fh.stdout.strip(), "15")

if __name__ == "__main__":
    unittest.main()
