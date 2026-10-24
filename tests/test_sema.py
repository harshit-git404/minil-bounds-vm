import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.sema import Sema, SemaError

class TestSema(unittest.TestCase):
    def test_valid_program(self):
        code = """
        int arr[50];
        int add(int a, int b) {
            int temp = a + b;
            return temp;
        }
        int main() {
            arr[0] = add(1, 2);
            print(arr[0]);
            return 0;
        }
        """
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        sema.analyze(ast)

        self.assertIn("arr", sema.global_arrays)
        self.assertIn("add", sema.functions)
        self.assertIn("main", sema.functions)

        # Check local slot allocation
        add_fn = sema.functions["add"]
        self.assertEqual(add_fn.slots["a"], 0)
        self.assertEqual(add_fn.slots["b"], 1)
        self.assertEqual(add_fn.slots["temp"], 2)

    def test_missing_main(self):
        code = "int foo() { return 1; }"
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        with self.assertRaises(SemaError):
            sema.analyze(ast)

    def test_undeclared_variable(self):
        code = "int main() { x = 10; return 0; }"
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        with self.assertRaises(SemaError):
            sema.analyze(ast)

    def test_undeclared_array(self):
        code = "int main() { arr[0] = 10; return 0; }"
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        with self.assertRaises(SemaError):
            sema.analyze(ast)

    def test_function_arity_mismatch(self):
        code = """
        int add(int a, int b) { return a + b; }
        int main() { return add(1); }
        """
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        with self.assertRaises(SemaError):
            sema.analyze(ast)

    def test_constant_bounds_diagnostic(self):
        code = """
        int a[10];
        int main() {
            a[15] = 42;
            int x = a[-2];
            return 0;
        }
        """
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        sema.analyze(ast)

        self.assertEqual(len(sema.diagnostics), 2)
        self.assertIn("constant index 15 is out of bounds", sema.diagnostics[0])
        self.assertIn("constant index -2 is out of bounds", sema.diagnostics[1])

if __name__ == "__main__":
    unittest.main()
