import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from compiler.lexer import Lexer
from compiler.parser import Parser, ParserError
from compiler.ast_nodes import (
    Program, GlobalArray, FuncDef, VarDeclStmt, AssignStmt, ArrayAssignStmt,
    IfStmt, WhileStmt, ReturnStmt, PrintStmt, BinaryExpr, ArrayAccessExpr, CallExpr
)

class TestParser(unittest.TestCase):
    def test_global_array_and_function(self):
        code = """
        int a[100];
        int b[200];

        int sum(int x, int y) {
            return x + y;
        }

        int main() {
            int res = sum(10, 20);
            print(res);
            return 0;
        }
        """
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()

        self.assertEqual(len(ast.global_arrays), 2)
        self.assertEqual(ast.global_arrays[0].name, "a")
        self.assertEqual(ast.global_arrays[0].size, 100)
        self.assertEqual(ast.global_arrays[1].name, "b")
        self.assertEqual(ast.global_arrays[1].size, 200)

        self.assertEqual(len(ast.functions), 2)
        self.assertEqual(ast.functions[0].name, "sum")
        self.assertEqual(len(ast.functions[0].params), 2)
        self.assertEqual(ast.functions[1].name, "main")

    def test_operator_precedence(self):
        code = """
        int main() {
            int x = 2 + 3 * 4;
            int y = (2 + 3) * 4;
            int z = 10 > 5 && 3 < 4 || 1 == 0;
            return 0;
        }
        """
        ast = Parser(Lexer(code).tokenize()).parse()
        main_func = ast.functions[0]

        # x = 2 + (3 * 4)
        stmt_x = main_func.body[0]
        self.assertIsInstance(stmt_x, VarDeclStmt)
        self.assertEqual(stmt_x.init_expr.op, "+")
        self.assertEqual(stmt_x.init_expr.right.op, "*")

        # y = (2 + 3) * 4
        stmt_y = main_func.body[1]
        self.assertEqual(stmt_y.init_expr.op, "*")
        self.assertEqual(stmt_y.init_expr.left.op, "+")

        # z = ((10 > 5) && (3 < 4)) || (1 == 0)
        stmt_z = main_func.body[2]
        self.assertEqual(stmt_z.init_expr.op, "||")
        self.assertEqual(stmt_z.init_expr.left.op, "&&")

    def test_array_access_and_assignment(self):
        code = """
        int arr[10];
        int main() {
            arr[0] = 42;
            int v = arr[0];
            return v;
        }
        """
        ast = Parser(Lexer(code).tokenize()).parse()
        main_body = ast.functions[0].body
        self.assertIsInstance(main_body[0], ArrayAssignStmt)
        self.assertEqual(main_body[0].name, "arr")
        self.assertEqual(main_body[0].site_id, 0)

        self.assertIsInstance(main_body[1], VarDeclStmt)
        self.assertIsInstance(main_body[1].init_expr, ArrayAccessExpr)
        self.assertEqual(main_body[1].init_expr.name, "arr")
        self.assertEqual(main_body[1].init_expr.site_id, 1)

    def test_syntax_errors(self):
        # Missing semicolon
        code = "int main() { int x = 5 }"
        with self.assertRaises(ParserError):
            Parser(Lexer(code).tokenize()).parse()

        # Non-positive array size
        code = "int a[0]; int main() { return 0; }"
        with self.assertRaises(ParserError):
            Parser(Lexer(code).tokenize()).parse()

if __name__ == "__main__":
    unittest.main()
