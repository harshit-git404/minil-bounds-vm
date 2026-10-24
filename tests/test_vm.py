"""
Integration and differential tests for MiniL compiler and VM.
Verifies:
1. Modes U, R, F produce identical stdout on all in-bounds programs.
2. Both dispatch implementations (SWITCH and GOTO) produce identical results.
3. Mode U runs silently on moderate out-of-bounds accesses without crashing.
4. Modes R and F trap identically (exit code 2, diagnostic message with pc and array name).
5. -DCOUNT correctly measures instructions and checks.
"""
import os
import subprocess
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VM_DEFAULT = os.path.join(ROOT_DIR, "vm", "minil-vm")
VM_GOTO = os.path.join(ROOT_DIR, "vm", "minil-vm-goto")
VM_SWITCH = os.path.join(ROOT_DIR, "vm", "minil-vm-switch")
VM_COUNT = os.path.join(ROOT_DIR, "vm", "minil-vm-count")

class TestVM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure VMs are built
        subprocess.check_call(["make", "vm"], cwd=ROOT_DIR)

    def _compile_and_run(self, source_path: str, mode: str, vm_bin: str):
        with tempfile.NamedTemporaryFile(suffix=".mbc", delete=False) as tmp:
            mbc_path = tmp.name

        try:
            # Compile
            comp_proc = subprocess.run(
                ["python3", "-m", "compiler.main", "--mode", mode, "-o", mbc_path, source_path],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True
            )
            self.assertEqual(comp_proc.returncode, 0, f"Compilation failed: {comp_proc.stderr}")

            # Run VM
            run_proc = subprocess.run(
                [vm_bin, mbc_path],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True
            )
            return run_proc
        finally:
            if os.path.exists(mbc_path):
                os.remove(mbc_path)

    def test_in_bounds_programs_equivalence(self):
        in_bounds_programs = [
            "arithmetic.minil",
            "control_flow.minil",
            "recursion.minil",
            "array_fill_sum.minil",
            "bubble_sort.minil",
        ]

        for prog in in_bounds_programs:
            prog_path = os.path.join(ROOT_DIR, "tests", "programs", prog)

            # Expected reference output from mode U with GOTO
            ref_proc = self._compile_and_run(prog_path, "U", VM_GOTO)
            self.assertEqual(ref_proc.returncode, 0, f"Failed on {prog}: {ref_proc.stderr}")
            expected_stdout = ref_proc.stdout

            # Test each mode and each VM variant
            for mode in ["U", "R", "F"]:
                for vm_bin in [VM_GOTO, VM_SWITCH]:
                    proc = self._compile_and_run(prog_path, mode, vm_bin)
                    self.assertEqual(proc.returncode, 0, f"{prog} failed in mode {mode}: {proc.stderr}")
                    self.assertEqual(
                        proc.stdout,
                        expected_stdout,
                        f"Output mismatch for {prog} in mode {mode} with {vm_bin}"
                    )
                    # Check timing is reported in stderr
                    self.assertIn("TIME_NS:", proc.stderr)
                    self.assertIn("TIME_S:", proc.stderr)

    def test_out_of_bounds_behavior(self):
        oob_programs = [
            "oob_read_high.minil",
            "oob_read_neg.minil",
            "oob_write_high.minil",
            "oob_write_neg.minil",
        ]

        for prog in oob_programs:
            prog_path = os.path.join(ROOT_DIR, "tests", "programs", prog)

            # Mode U: runs silently to completion (exit code 0)
            proc_u = self._compile_and_run(prog_path, "U", VM_GOTO)
            self.assertEqual(
                proc_u.returncode, 0,
                f"Mode U should run silently without crashing on {prog}, got {proc_u.returncode}"
            )

            # Mode R: traps with exit code 2 and bounds check message
            proc_r = self._compile_and_run(prog_path, "R", VM_GOTO)
            self.assertEqual(proc_r.returncode, 2, f"Mode R should trap with exit code 2 on {prog}")
            self.assertIn("TRAP: bounds check failed for array 'a'", proc_r.stderr)
            self.assertIn("at pc", proc_r.stderr)

            # Mode F: traps with exit code 2 and bounds check message
            proc_f = self._compile_and_run(prog_path, "F", VM_GOTO)
            self.assertEqual(proc_f.returncode, 2, f"Mode F should trap with exit code 2 on {prog}")
            self.assertIn("TRAP: bounds check failed for array 'a'", proc_f.stderr)
            self.assertIn("at pc", proc_f.stderr)

            # Switch dispatch should also trap identically
            proc_r_sw = self._compile_and_run(prog_path, "R", VM_SWITCH)
            self.assertEqual(proc_r_sw.returncode, 2)
            self.assertIn("TRAP: bounds check failed for array 'a'", proc_r_sw.stderr)

    def test_instrumented_counts(self):
        prog_path = os.path.join(ROOT_DIR, "tests", "programs", "array_fill_sum.minil")

        # In array_fill_sum.minil:
        # 50 stores in loop 1, 50 loads in loop 2 = 100 array accesses
        proc_u = self._compile_and_run(prog_path, "U", VM_COUNT)
        proc_r = self._compile_and_run(prog_path, "R", VM_COUNT)
        proc_f = self._compile_and_run(prog_path, "F", VM_COUNT)

        def parse_counts(stderr):
            counts = {}
            for line in stderr.splitlines():
                if line.startswith("INSTR_COUNT:"):
                    counts["instr"] = int(line.split(":")[1].strip())
                elif line.startswith("CHECK_COUNT:"):
                    counts["check"] = int(line.split(":")[1].strip())
            return counts

        counts_u = parse_counts(proc_u.stderr)
        counts_r = parse_counts(proc_r.stderr)
        counts_f = parse_counts(proc_f.stderr)

        self.assertEqual(counts_u["check"], 0)
        self.assertEqual(counts_r["check"], 100)
        self.assertEqual(counts_f["check"], 100)

        # R dispatches an extra CHK instruction per access compared to F
        # So counts_r['instr'] == counts_f['instr'] + 100
        self.assertEqual(counts_r["instr"] - counts_f["instr"], 100)
        # F has same instruction count as U
        self.assertEqual(counts_f["instr"], counts_u["instr"])

if __name__ == "__main__":
    unittest.main()
