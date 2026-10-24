"""
Unit tests for MiniL Interval Analysis and Classification.
"""
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.sema import Sema
from compiler.analysis import Interval, IntervalAnalysis

class TestIntervalAnalysis(unittest.TestCase):
    def _run_analysis(self, source: str):
        ast = Parser(Lexer(source).tokenize()).parse()
        sema = Sema()
        sema.analyze(ast)
        analysis = IntervalAnalysis(sema)
        report = analysis.analyze(ast)
        return report, analysis

    def test_interval_arithmetic(self):
        # Truncating division
        pos = Interval(10, 20)
        neg = Interval(-5, -2)
        div_res = pos.div(neg)
        # 10/-2 = -5, 20/-5 = -4, 20/-2 = -10, 10/-5 = -2 -> [-10, -2]
        self.assertEqual(div_res.low, -10.0)
        self.assertEqual(div_res.high, -2.0)

        # C-style remainder
        # x % 64 for unknown signed x is within [-63, 63]
        top_x = Interval.top()
        rem_res = top_x.mod(Interval.const(64))
        self.assertEqual(rem_res.low, -63.0)
        self.assertEqual(rem_res.high, 63.0)

    def test_statically_safe_loop(self):
        code = """
        int a[50];
        int main() {
            int i = 0;
            while (i < 50) {
                a[i] = i * 2;
                i = i + 1;
            }
            return 0;
        }
        """
        report, analysis = self._run_analysis(code)
        self.assertEqual(report["summary"]["total_sites"], 1)
        self.assertEqual(report["summary"]["safe"], 1)
        self.assertEqual(report["summary"]["violation"], 0)
        self.assertEqual(report["summary"]["unknown"], 0)
        self.assertEqual(report["sites"][0]["classification"], "safe")

    def test_statically_definite_violation(self):
        code = """
        int a[10];
        int main() {
            int i = 15;
            a[i] = 42;
            return 0;
        }
        """
        report, analysis = self._run_analysis(code)
        self.assertEqual(report["summary"]["violation"], 1)
        self.assertEqual(report["sites"][0]["classification"], "violation")

    def test_bubble_sort_inner_loop(self):
        code = """
        int a[10];
        int main() {
            int n = 10;
            int i = 0;
            while (i < n - 1) {
                int j = 0;
                while (j < n - 1 - i) {
                    int t = a[j];
                    int t2 = a[j + 1];
                    j = j + 1;
                }
                i = i + 1;
            }
            return 0;
        }
        """
        report, analysis = self._run_analysis(code)
        # All array accesses in bubble sort with constant bounds are statically provable safe
        self.assertEqual(report["summary"]["total_sites"], 2)
        self.assertEqual(report["summary"]["safe"], 2)

    def test_unknown_sites(self):
        # 1. Parameter bound
        # 2. Data-dependent index from array load
        code = """
        int a[100];
        int p[100];
        int func(int m) {
            int i = 0;
            while (i < m) {
                int idx = p[i];
                a[idx] = 1;
                i = i + 1;
            }
            return 0;
        }
        int main() {
            return func(50);
        }
        """
        report, analysis = self._run_analysis(code)
        # p[i]: i in [0, m-1] where m is param (TOP) -> unknown
        # a[idx]: idx is loaded from p -> unknown
        self.assertEqual(report["summary"]["safe"], 0)
        self.assertEqual(report["summary"]["unknown"], 2)

if __name__ == "__main__":
    unittest.main()
