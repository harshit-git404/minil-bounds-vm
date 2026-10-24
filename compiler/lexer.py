"""
Lexer for the MiniL language.
"""
from enum import Enum, auto
from typing import List, Optional

class TokenType(Enum):
    # Keywords
    KW_INT = auto()
    KW_IF = auto()
    KW_ELSE = auto()
    KW_WHILE = auto()
    KW_RETURN = auto()
    KW_PRINT = auto()

    # Identifiers and Literals
    IDENT = auto()
    INT_LIT = auto()

    # Operators
    PLUS = auto()      # +
    MINUS = auto()     # -
    STAR = auto()      # *
    SLASH = auto()     # /
    PERCENT = auto()   # %
    ASSIGN = auto()    # =
    EQ = auto()        # ==
    NE = auto()        # !=
    LT = auto()        # <
    LE = auto()        # <=
    GT = auto()        # >
    GE = auto()        # >=
    AND = auto()       # &&
    OR = auto()        # ||
    NOT = auto()       # !

    # Delimiters
    LPAREN = auto()    # (
    RPAREN = auto()    # )
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]
    LBRACE = auto()    # {
    RBRACE = auto()    # }
    SEMICOLON = auto() # ;
    COMMA = auto()     # ,

    EOF = auto()

KEYWORDS = {
    "int": TokenType.KW_INT,
    "if": TokenType.KW_IF,
    "else": TokenType.KW_ELSE,
    "while": TokenType.KW_WHILE,
    "return": TokenType.KW_RETURN,
    "print": TokenType.KW_PRINT,
}

class Token:
    def __init__(self, type_: TokenType, value: any, line: int, col: int):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line}, col={self.col})"

class LexerError(Exception):
    def __init__(self, message: str, line: int, col: int):
        super().__init__(f"Lexer error at line {line}, col {col}: {message}")
        self.line = line
        self.col = col

class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(source)

    def _peek(self) -> Optional[str]:
        if self.pos < self.length:
            return self.source[self.pos]
        return None

    def _peek_next(self) -> Optional[str]:
        if self.pos + 1 < self.length:
            return self.source[self.pos + 1]
        return None

    def _advance(self) -> Optional[str]:
        ch = self._peek()
        if ch is not None:
            self.pos += 1
            if ch == '\n':
                self.line += 1
                self.col = 1
            else:
                self.col += 1
        return ch

    def _skip_whitespace_and_comments(self):
        while self.pos < self.length:
            ch = self._peek()
            if ch in ' \t\r\n':
                self._advance()
            elif ch == '/' and self._peek_next() == '/':
                # Single-line comment
                while self.pos < self.length and self._peek() != '\n':
                    self._advance()
            elif ch == '/' and self._peek_next() == '*':
                # Multi-line comment
                start_line, start_col = self.line, self.col
                self._advance() # consume /
                self._advance() # consume *
                closed = False
                while self.pos < self.length:
                    if self._peek() == '*' and self._peek_next() == '/':
                        self._advance()
                        self._advance()
                        closed = True
                        break
                    self._advance()
                if not closed:
                    raise LexerError("Unterminated multi-line comment", start_line, start_col)
            else:
                break

    def tokenize(self) -> List[Token]:
        tokens = []
        while True:
            self._skip_whitespace_and_comments()
            if self.pos >= self.length:
                tokens.append(Token(TokenType.EOF, "", self.line, self.col))
                break

            start_line, start_col = self.line, self.col
            ch = self._peek()

            # Identifiers and keywords
            if ch.isalpha() or ch == '_':
                ident = []
                while self._peek() is not None and (self._peek().isalnum() or self._peek() == '_'):
                    ident.append(self._advance())
                word = "".join(ident)
                token_type = KEYWORDS.get(word, TokenType.IDENT)
                tokens.append(Token(token_type, word, start_line, start_col))
                continue

            # Integer literals
            if ch.isdigit():
                digits = []
                while self._peek() is not None and self._peek().isdigit():
                    digits.append(self._advance())
                num_str = "".join(digits)
                tokens.append(Token(TokenType.INT_LIT, int(num_str), start_line, start_col))
                continue

            # Two-character or one-character operators
            if ch == '=':
                self._advance()
                if self._peek() == '=':
                    self._advance()
                    tokens.append(Token(TokenType.EQ, "==", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.ASSIGN, "=", start_line, start_col))
            elif ch == '!':
                self._advance()
                if self._peek() == '=':
                    self._advance()
                    tokens.append(Token(TokenType.NE, "!=", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.NOT, "!", start_line, start_col))
            elif ch == '<':
                self._advance()
                if self._peek() == '=':
                    self._advance()
                    tokens.append(Token(TokenType.LE, "<=", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.LT, "<", start_line, start_col))
            elif ch == '>':
                self._advance()
                if self._peek() == '=':
                    self._advance()
                    tokens.append(Token(TokenType.GE, ">=", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.GT, ">", start_line, start_col))
            elif ch == '&':
                self._advance()
                if self._peek() == '&':
                    self._advance()
                    tokens.append(Token(TokenType.AND, "&&", start_line, start_col))
                else:
                    raise LexerError(f"Unexpected character '&', expected '&&'", start_line, start_col)
            elif ch == '|':
                self._advance()
                if self._peek() == '|':
                    self._advance()
                    tokens.append(Token(TokenType.OR, "||", start_line, start_col))
                else:
                    raise LexerError(f"Unexpected character '|', expected '||'", start_line, start_col)
            elif ch == '+':
                self._advance()
                tokens.append(Token(TokenType.PLUS, "+", start_line, start_col))
            elif ch == '-':
                self._advance()
                tokens.append(Token(TokenType.MINUS, "-", start_line, start_col))
            elif ch == '*':
                self._advance()
                tokens.append(Token(TokenType.STAR, "*", start_line, start_col))
            elif ch == '/':
                self._advance()
                tokens.append(Token(TokenType.SLASH, "/", start_line, start_col))
            elif ch == '%':
                self._advance()
                tokens.append(Token(TokenType.PERCENT, "%", start_line, start_col))
            elif ch == '(':
                self._advance()
                tokens.append(Token(TokenType.LPAREN, "(", start_line, start_col))
            elif ch == ')':
                self._advance()
                tokens.append(Token(TokenType.RPAREN, ")", start_line, start_col))
            elif ch == '[':
                self._advance()
                tokens.append(Token(TokenType.LBRACKET, "[", start_line, start_col))
            elif ch == ']':
                self._advance()
                tokens.append(Token(TokenType.RBRACKET, "]", start_line, start_col))
            elif ch == '{':
                self._advance()
                tokens.append(Token(TokenType.LBRACE, "{", start_line, start_col))
            elif ch == '}':
                self._advance()
                tokens.append(Token(TokenType.RBRACE, "}", start_line, start_col))
            elif ch == ';':
                self._advance()
                tokens.append(Token(TokenType.SEMICOLON, ";", start_line, start_col))
            elif ch == ',':
                self._advance()
                tokens.append(Token(TokenType.COMMA, ",", start_line, start_col))
            else:
                self._advance()
                raise LexerError(f"Unexpected character: {ch!r}", start_line, start_col)

        return tokens
