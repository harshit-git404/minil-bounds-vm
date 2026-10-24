import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.sema import Sema
from compiler.codegen import CodeGenerator
from compiler.opcodes import *

class TestCodeGen(unittest.TestCase):
    def _compile(self, code: str, mode: str):
        ast = Parser(Lexer(code).tokenize()).parse()
        sema = Sema()
        sema.analyze(ast)
        codegen = CodeGenerator(sema, mode=mode)
        instructions = codegen.generate(ast)
        return instructions, codegen

    def test_mode_u_codegen(self):
        code = """
        int a[10];
        int main() {
            a[0] = 42;
            int x = a[0];
            return x;
        }
        """
        insns, _ = self._compile(code, "U")
        opcodes = [op for op, a, b in insns]

        self.assertNotIn(OP_CHK, opcodes)
        self.assertNotIn(OP_ALOADC, opcodes)
        self.assertNotIn(OP_ASTOREC, opcodes)
        self.assertIn(OP_ASTORE, opcodes)
        self.assertIn(OP_ALOAD, opcodes)

    def test_mode_r_codegen(self):
        code = """
        int a[10];
        int main() {
            a[0] = 42;
            int x = a[0];
            return x;
        }
        """
        insns, _ = self._compile(code, "R")
        opcodes = [op for op, a, b in insns]

        self.assertIn(OP_CHK, opcodes)
        self.assertIn(OP_ASTORE, opcodes)
        self.assertIn(OP_ALOAD, opcodes)
        self.assertNotIn(OP_ALOADC, opcodes)
        self.assertNotIn(OP_ASTOREC, opcodes)

        # Check that CHK immediately precedes ASTORE and ALOAD
        for i, op in enumerate(opcodes):
            if op in (OP_ALOAD, OP_ASTORE):
                self.assertEqual(opcodes[i - 1], OP_CHK)

    def test_mode_f_codegen(self):
        code = """
        int a[10];
        int main() {
            a[0] = 42;
            int x = a[0];
            return x;
        }
        """
        insns, _ = self._compile(code, "F")
        opcodes = [op for op, a, b in insns]

        self.assertNotIn(OP_CHK, opcodes)
        self.assertNotIn(OP_ALOAD, opcodes)
        self.assertNotIn(OP_ASTORE, opcodes)
        self.assertIn(OP_ASTOREC, opcodes)
        self.assertIn(OP_ALOADC, opcodes)

if __name__ == "__main__":
    unittest.main()
