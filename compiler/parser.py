"""
Recursive descent parser for MiniL.
"""
from typing import List, Optional
from compiler.lexer import Token, TokenType, Lexer, LexerError
from compiler.ast_nodes import (
    Program, GlobalArray, FuncDef, Param, Stmt, Expr,
    VarDeclStmt, AssignStmt, ArrayAssignStmt, IfStmt, WhileStmt,
    ReturnStmt, PrintStmt, ExprStmt, BlockStmt,
    IntLit, VarExpr, ArrayAccessExpr, UnaryExpr, BinaryExpr, CallExpr
)

class ParserError(Exception):
    def __init__(self, message: str, token: Token):
        super().__init__(f"Parser error at line {token.line}, col {token.col}: {message}")
        self.token = token

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.site_id_counter = 0

    def _next_site_id(self) -> int:
        sid = self.site_id_counter
        self.site_id_counter += 1
        return sid

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _check(self, type_: TokenType) -> bool:
        return self._peek().type == type_

    def _advance(self) -> Token:
        tok = self._peek()
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _match(self, *types: TokenType) -> bool:
        for t in types:
            if self._check(t):
                self._advance()
                return True
        return False

    def _expect(self, type_: TokenType, msg: str) -> Token:
        tok = self._peek()
        if tok.type != type_:
            raise ParserError(f"Expected {msg}, got {tok.type.name} ({tok.value!r})", tok)
        return self._advance()

    def parse(self) -> Program:
        global_arrays = []
        functions = []

        while not self._check(TokenType.EOF):
            # Both global arrays and functions start with 'int'
            start_tok = self._expect(TokenType.KW_INT, "'int'")
            ident_tok = self._expect(TokenType.IDENT, "identifier")

            if self._check(TokenType.LBRACKET):
                # Global array declaration: int name[size];
                self._advance() # consume '['
                size_tok = self._expect(TokenType.INT_LIT, "integer array size")
                if size_tok.value <= 0:
                    raise ParserError(f"Array size must be positive, got {size_tok.value}", size_tok)
                self._expect(TokenType.RBRACKET, "']'")
                self._expect(TokenType.SEMICOLON, "';'")
                global_arrays.append(GlobalArray(
                    line=start_tok.line,
                    col=start_tok.col,
                    name=ident_tok.value,
                    size=size_tok.value
                ))
            elif self._check(TokenType.LPAREN):
                # Function definition: int name(params) { ... }
                self._advance() # consume '('
                params = []
                if not self._check(TokenType.RPAREN):
                    while True:
                        p_type = self._expect(TokenType.KW_INT, "'int'")
                        p_name = self._expect(TokenType.IDENT, "parameter name")
                        params.append(Param(line=p_type.line, col=p_type.col, name=p_name.value))
                        if not self._match(TokenType.COMMA):
                            break
                self._expect(TokenType.RPAREN, "')'")
                self._expect(TokenType.LBRACE, "'{'")
                body = []
                while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
                    body.append(self._parse_statement())
                self._expect(TokenType.RBRACE, "'}'")

                functions.append(FuncDef(
                    line=start_tok.line,
                    col=start_tok.col,
                    name=ident_tok.value,
                    params=params,
                    body=body
                ))
            else:
                raise ParserError(f"Expected '[' for array or '(' for function, got {self._peek().value!r}", self._peek())

        return Program(global_arrays=global_arrays, functions=functions)

    def _parse_statement(self) -> Stmt:
        tok = self._peek()

        if tok.type == TokenType.LBRACE:
            self._advance()
            stmts = []
            while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
                stmts.append(self._parse_statement())
            self._expect(TokenType.RBRACE, "'}'")
            return BlockStmt(line=tok.line, col=tok.col, stmts=stmts)

        if tok.type == TokenType.KW_INT:
            # Local variable declaration: int x; or int x = expr;
            self._advance()
            name_tok = self._expect(TokenType.IDENT, "variable name")
            init_expr = None
            if self._match(TokenType.ASSIGN):
                init_expr = self._parse_expression()
            self._expect(TokenType.SEMICOLON, "';'")
            return VarDeclStmt(line=tok.line, col=tok.col, name=name_tok.value, init_expr=init_expr)

        if tok.type == TokenType.KW_IF:
            self._advance()
            self._expect(TokenType.LPAREN, "'('")
            cond = self._parse_expression()
            self._expect(TokenType.RPAREN, "')'")
            then_branch = self._parse_statement()
            else_branch = None
            if self._match(TokenType.KW_ELSE):
                else_branch = self._parse_statement()
            return IfStmt(line=tok.line, col=tok.col, cond=cond, then_branch=then_branch, else_branch=else_branch)

        if tok.type == TokenType.KW_WHILE:
            self._advance()
            self._expect(TokenType.LPAREN, "'('")
            cond = self._parse_expression()
            self._expect(TokenType.RPAREN, "')'")
            body = self._parse_statement()
            return WhileStmt(line=tok.line, col=tok.col, cond=cond, body=body)

        if tok.type == TokenType.KW_RETURN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.SEMICOLON, "';'")
            return ReturnStmt(line=tok.line, col=tok.col, expr=expr)

        if tok.type == TokenType.KW_PRINT:
            self._advance()
            self._expect(TokenType.LPAREN, "'('")
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "')'")
            self._expect(TokenType.SEMICOLON, "';'")
            return PrintStmt(line=tok.line, col=tok.col, expr=expr)

        # Assignment or Expression Statement
        # Lookahead to distinguish var = expr vs a[idx] = expr vs expr;
        if tok.type == TokenType.IDENT:
            # Check if followed by '=' -> AssignStmt
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == TokenType.ASSIGN:
                name_tok = self._advance()
                self._advance() # consume '='
                val_expr = self._parse_expression()
                self._expect(TokenType.SEMICOLON, "';'")
                return AssignStmt(line=tok.line, col=tok.col, name=name_tok.value, expr=val_expr)
            elif self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == TokenType.LBRACKET:
                # Could be a[idx] = expr; or expression a[idx] + 1;
                # Let's see if this is an array assignment
                # We can parse the expression and check if it's ArrayAccess followed by '='
                expr = self._parse_expression()
                if self._match(TokenType.ASSIGN):
                    if not isinstance(expr, ArrayAccessExpr):
                        raise ParserError("Invalid lvalue for assignment", tok)
                    val_expr = self._parse_expression()
                    self._expect(TokenType.SEMICOLON, "';'")
                    return ArrayAssignStmt(
                        line=expr.line,
                        col=expr.col,
                        name=expr.name,
                        index_expr=expr.index_expr,
                        expr=val_expr,
                        site_id=expr.site_id
                    )
                else:
                    self._expect(TokenType.SEMICOLON, "';'")
                    return ExprStmt(line=tok.line, col=tok.col, expr=expr)

        # General expression statement
        expr = self._parse_expression()
        self._expect(TokenType.SEMICOLON, "';'")
        return ExprStmt(line=tok.line, col=tok.col, expr=expr)

    def _parse_expression(self) -> Expr:
        return self._parse_logical_or()

    def _parse_logical_or(self) -> Expr:
        expr = self._parse_logical_and()
        while self._match(TokenType.OR):
            op = "||"
            right = self._parse_logical_and()
            expr = BinaryExpr(line=expr.line, col=expr.col, op=op, left=expr, right=right)
        return expr

    def _parse_logical_and(self) -> Expr:
        expr = self._parse_equality()
        while self._match(TokenType.AND):
            op = "&&"
            right = self._parse_equality()
            expr = BinaryExpr(line=expr.line, col=expr.col, op=op, left=expr, right=right)
        return expr

    def _parse_equality(self) -> Expr:
        expr = self._parse_relational()
        while self._check(TokenType.EQ) or self._check(TokenType.NE):
            tok = self._advance()
            right = self._parse_relational()
            expr = BinaryExpr(line=expr.line, col=expr.col, op=tok.value, left=expr, right=right)
        return expr

    def _parse_relational(self) -> Expr:
        expr = self._parse_additive()
        while self._check(TokenType.LT) or self._check(TokenType.LE) or \
              self._check(TokenType.GT) or self._check(TokenType.GE):
            tok = self._advance()
            right = self._parse_additive()
            expr = BinaryExpr(line=expr.line, col=expr.col, op=tok.value, left=expr, right=right)
        return expr

    def _parse_additive(self) -> Expr:
        expr = self._parse_multiplicative()
        while self._check(TokenType.PLUS) or self._check(TokenType.MINUS):
            tok = self._advance()
            right = self._parse_multiplicative()
            expr = BinaryExpr(line=expr.line, col=expr.col, op=tok.value, left=expr, right=right)
        return expr

    def _parse_multiplicative(self) -> Expr:
        expr = self._parse_unary()
        while self._check(TokenType.STAR) or self._check(TokenType.SLASH) or self._check(TokenType.PERCENT):
            tok = self._advance()
            right = self._parse_unary()
            expr = BinaryExpr(line=expr.line, col=expr.col, op=tok.value, left=expr, right=right)
        return expr

    def _parse_unary(self) -> Expr:
        tok = self._peek()
        if tok.type in (TokenType.MINUS, TokenType.NOT, TokenType.PLUS):
            self._advance()
            operand = self._parse_unary()
            if tok.type == TokenType.PLUS:
                return operand
            return UnaryExpr(line=tok.line, col=tok.col, op=tok.value, expr=operand)
        return self._parse_primary()

    def _parse_primary(self) -> Expr:
        tok = self._peek()

        if tok.type == TokenType.INT_LIT:
            self._advance()
            return IntLit(line=tok.line, col=tok.col, val=tok.value)

        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "')'")
            return expr

        if tok.type == TokenType.IDENT:
            ident_tok = self._advance()
            # Function call
            if self._match(TokenType.LPAREN):
                args = []
                if not self._check(TokenType.RPAREN):
                    while True:
                        args.append(self._parse_expression())
                        if not self._match(TokenType.COMMA):
                            break
                self._expect(TokenType.RPAREN, "')'")
                return CallExpr(line=ident_tok.line, col=ident_tok.col, name=ident_tok.value, args=args)
            # Array read
            elif self._match(TokenType.LBRACKET):
                idx_expr = self._parse_expression()
                self._expect(TokenType.RBRACKET, "']'")
                return ArrayAccessExpr(
                    line=ident_tok.line,
                    col=ident_tok.col,
                    name=ident_tok.value,
                    index_expr=idx_expr,
                    site_id=self._next_site_id()
                )
            # Plain variable
            else:
                return VarExpr(line=ident_tok.line, col=ident_tok.col, name=ident_tok.value)

        raise ParserError(f"Unexpected token {tok.type.name} ({tok.value!r}) in expression", tok)
