# MiniL Grammar Specification

This document defines the formal lexical and syntactic grammar of the **MiniL** programming language.

## 1. Lexical Grammar

### 1.1 Comments and Whitespace
- Single-line comments start with `//` and extend to the end of the line.
- Multi-line comments are delimited by `/*` and `*/` (nesting is not supported).
- Whitespace consists of spaces, tabs, carriage returns, and newlines. Whitespace is ignored except as a token separator.

### 1.2 Identifiers and Keywords
- **Identifiers** match `[a-zA-Z_][a-zA-Z0-9_]*`.
- **Keywords**:
  - Types: `int`
  - Control flow: `if`, `else`, `while`, `return`
  - Built-in functions: `print`

### 1.3 Literals
- **Integer Literals**: Decimal numbers matching `[0-9]+`.
  - All integers are 64-bit signed two's-complement (`int64_t`).

### 1.4 Operators and Delimiters
- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Relational: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Logical: `&&`, `||`, `!`
- Assignment: `=`
- Punctuation: `;`, `,`, `(`, `)`, `[`, `]`, `{`, `}`

---

## 2. Syntactic Grammar (EBNF)

```ebnf
Program ::= ( GlobalArrayDecl | FunctionDef )*

GlobalArrayDecl ::= "int" IDENTIFIER "[" INTEGER_LITERAL "]" ";"

FunctionDef ::= "int" IDENTIFIER "(" ParameterList? ")" "{" Statement* "}"

ParameterList ::= Parameter ( "," Parameter )*
Parameter     ::= "int" IDENTIFIER

Statement ::= VarDeclStmt
            | AssignStmt
            | IfStmt
            | WhileStmt
            | ReturnStmt
            | PrintStmt
            | ExprStmt
            | BlockStmt

VarDeclStmt ::= "int" IDENTIFIER ( "=" Expression )? ";"

AssignStmt  ::= IDENTIFIER "=" Expression ";"
              | IDENTIFIER "[" Expression "]" "=" Expression ";"

IfStmt      ::= "if" "(" Expression ")" Statement ( "else" Statement )?

WhileStmt   ::= "while" "(" Expression ")" Statement

ReturnStmt  ::= "return" Expression ";"

PrintStmt   ::= "print" "(" Expression ")" ";"

ExprStmt    ::= Expression ";"

BlockStmt   ::= "{" Statement* "}"

Expression  ::= LogicalOrExpr

LogicalOrExpr  ::= LogicalAndExpr ( "||" LogicalAndExpr )*

LogicalAndExpr ::= EqualityExpr ( "&&" EqualityExpr )*

EqualityExpr   ::= RelationalExpr ( ( "==" | "!=" ) RelationalExpr )*

RelationalExpr ::= AdditiveExpr ( ( "<" | "<=" | ">" | ">=" ) AdditiveExpr )*

AdditiveExpr   ::= MultiplicativeExpr ( ( "+" | "-" ) MultiplicativeExpr )*

MultiplicativeExpr ::= UnaryExpr ( ( "*" | "/" | "%" ) UnaryExpr )*

UnaryExpr      ::= ( "-" | "!" | "+" ) UnaryExpr
                 | PrimaryExpr

PrimaryExpr    ::= INTEGER_LITERAL
                 | IDENTIFIER "(" ArgumentList? ")"
                 | IDENTIFIER "[" Expression "]"
                 | IDENTIFIER
                 | "(" Expression ")"

ArgumentList   ::= Expression ( "," Expression )*
```

---

## 3. Semantics and Types

1. **Types**:
   - Scalars: 64-bit signed integers (`int`).
   - Arrays: Globally declared, fixed-size 1D arrays of `int`.
   - Functions: Take zero or more `int` parameters and return `int`.

2. **Scoping**:
   - Global scope: Global array identifiers and function names.
   - Function scope: Parameters and local variables.
   - Variable shadowing: Local variables shadow globals with the same name. Local variable names within a function must be unique.

3. **Evaluation Rules**:
   - Boolean expressions evaluate to `1` (true) and `0` (false).
   - In conditions (`if`, `while`, `!`, `&&`, `||`), any non-zero integer is treated as true, and `0` is treated as false.
   - `&&` and `||` evaluate with standard short-circuit semantics.
   - Arithmetic `/` and `%` perform standard C99/C11 integer truncation toward zero. Division or remainder by zero triggers a runtime error.
   - Array accesses `a[i]` and `a[i] = v` evaluate index `i`. Out-of-bounds accesses are checked according to the compilation mode (`U`, `R`, `F`, `S`, `H`).

4. **Program Entry Point**:
   - Every complete program must define an `int main()` function taking no arguments (or ignoring arguments).
