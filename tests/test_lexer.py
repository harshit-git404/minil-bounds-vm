import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from compiler.lexer import Lexer, TokenType, LexerError

class TestLexer(unittest.TestCase):
    def test_keywords_and_identifiers(self):
        code = "int if else while return print my_var foo123"
        tokens = Lexer(code).tokenize()
        types = [t.type for t in tokens]
        expected = [
            TokenType.KW_INT, TokenType.KW_IF, TokenType.KW_ELSE,
            TokenType.KW_WHILE, TokenType.KW_RETURN, TokenType.KW_PRINT,
            TokenType.IDENT, TokenType.IDENT, TokenType.EOF
        ]
        self.assertEqual(types, expected)
        self.assertEqual(tokens[6].value, "my_var")
        self.assertEqual(tokens[7].value, "foo123")

    def test_literals_and_operators(self):
        code = "123 + 456 - 7 * 8 / 9 % 10 == != < <= > >= && || ! = ; , ( ) [ ] { }"
        tokens = Lexer(code).tokenize()
        types = [t.type for t in tokens]
        expected = [
            TokenType.INT_LIT, TokenType.PLUS, TokenType.INT_LIT, TokenType.MINUS,
            TokenType.INT_LIT, TokenType.STAR, TokenType.INT_LIT, TokenType.SLASH,
            TokenType.INT_LIT, TokenType.PERCENT, TokenType.INT_LIT,
            TokenType.EQ, TokenType.NE, TokenType.LT, TokenType.LE,
            TokenType.GT, TokenType.GE, TokenType.AND, TokenType.OR,
            TokenType.NOT, TokenType.ASSIGN,
            TokenType.SEMICOLON, TokenType.COMMA,
            TokenType.LPAREN, TokenType.RPAREN,
            TokenType.LBRACKET, TokenType.RBRACKET,
            TokenType.LBRACE, TokenType.RBRACE,
            TokenType.EOF
        ]
        self.assertEqual(types, expected)
        self.assertEqual(tokens[0].value, 123)
        self.assertEqual(tokens[2].value, 456)

    def test_comments(self):
        code = """
        // Single line comment
        int x = 42; // Another comment
        /* Multi-line
           comment here */
        int y = 100;
        """
        tokens = Lexer(code).tokenize()
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        self.assertEqual(len(types), 10) # int x = 42 ; int y = 100 ;

    def test_unterminated_comment(self):
        code = "/* unclosed comment"
        with self.assertRaises(LexerError):
            Lexer(code).tokenize()

    def test_invalid_character(self):
        code = "int x = @123;"
        with self.assertRaises(LexerError):
            Lexer(code).tokenize()

if __name__ == "__main__":
    unittest.main()
