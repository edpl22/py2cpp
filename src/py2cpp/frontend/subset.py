"""Structural subset validation.

This pass answers only "is this syntax shape permitted by the v1 subset",
independent of what any name resolves to or what type anything has. Name
resolution and type checking happen later (see semantic/collect.py and
ir/lower.py) and can assume the tree already satisfies these shape rules.

Notable scoping restrictions for this milestone (documented rather than
silently applied):

- 'return' may only appear as the final statement of a function's own
  top-level body -- never nested inside if/while/for, and never more than
  once. Early/multiple return points are a future milestone; this keeps
  every function body a straight sequence ending in one return, which
  keeps definite-assignment and codegen simple while still allowing rich
  conditional logic to compute the value that gets returned.
- chained comparisons ('a < b < c') are rejected: naively translating them
  to C++ would silently compute '(a < b) < c' instead of Python's
  '(a < b) and (b < c)', which is exactly the kind of silent behavioral
  divergence this project refuses to produce.
- 'and'/'or'/'not' require bool operands (i.e. comparison results),
  not Python's general "return one of the operands" semantics -- that
  would need either double-evaluating the left operand or a place to
  stash a temporary, neither of which this milestone's expression-only
  IR has.
- a 'for' loop's 'step' argument, when given, must be a compile-time
  integer literal, so the loop's direction (< vs >) can be chosen
  statically instead of needing a runtime branch.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.literals import extract_int_literal
from py2cpp.frontend.loader import SourceFile

_ALLOWED_BINOPS: tuple[type[ast.operator], ...] = (ast.Add, ast.Sub, ast.Mult)
_ALLOWED_COMPARE_OPS: tuple[type[ast.cmpop], ...] = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def validate_subset(tree: ast.Module, source: SourceFile, diagnostics: DiagnosticEngine) -> None:
    _SubsetValidator(source, diagnostics).visit(tree)


class _SubsetValidator(ast.NodeVisitor):
    def __init__(self, source: SourceFile, diagnostics: DiagnosticEngine) -> None:
        self._source = source
        self._diagnostics = diagnostics

    def _location(self, node: ast.AST) -> SourceLocation:
        return SourceLocation(
            filename=self._source.path,
            line=getattr(node, "lineno", 1),
            column=getattr(node, "col_offset", 0) + 1,
        )

    def _reject(self, node: ast.AST, message: str, help_text: str | None = None) -> None:
        self._diagnostics.error(codes.UNSUPPORTED_SYNTAX, message, self._location(node), help_text)

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef):
                self._validate_function(stmt)
            else:
                self._validate_stmt(stmt, allow_return=False)

    def _validate_function(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            self._reject(node.decorator_list[0], "decorators are not supported")

        args = node.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs or args.defaults:
            self._reject(
                node,
                "only plain positional parameters are supported "
                "(no *args, **kwargs, defaults, or keyword-only parameters)",
            )

        if not node.body:
            self._reject(node, "function body must not be empty")
            return
        self._validate_block(node.body, allow_return=True)

    def _validate_block(self, stmts: list[ast.stmt], *, allow_return: bool) -> None:
        last_index = len(stmts) - 1
        for i, stmt in enumerate(stmts):
            self._validate_stmt(stmt, allow_return=allow_return and i == last_index)

    def _validate_stmt(self, stmt: ast.stmt, *, allow_return: bool) -> None:
        if isinstance(stmt, ast.Return):
            if not allow_return:
                self._reject(
                    stmt,
                    "'return' may only appear as the final statement of a function body "
                    "in this milestone",
                    help_text="early/multiple return points arrive in a later milestone",
                )
                return
            if stmt.value is None:
                self._reject(stmt, "'return' must return a value")
                return
            self._validate_expr(stmt.value)
        elif isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                self._reject(
                    stmt, "only simple 'name = value' assignment is supported in this milestone"
                )
                return
            self._validate_expr(stmt.value)
        elif isinstance(stmt, ast.AnnAssign):
            if not isinstance(stmt.target, ast.Name):
                self._reject(
                    stmt,
                    "only simple 'name: type = value' assignment is supported in this milestone",
                )
                return
            if stmt.value is None:
                self._reject(stmt, "annotated assignment must have a value in this milestone")
                return
            self._validate_expr(stmt.value)
        elif isinstance(stmt, ast.If):
            self._validate_expr(stmt.test)
            self._validate_block(stmt.body, allow_return=False)
            self._validate_block(stmt.orelse, allow_return=False)
        elif isinstance(stmt, ast.While):
            if stmt.orelse:
                self._reject(stmt, "'while ... else' is not supported")
            self._validate_expr(stmt.test)
            self._validate_block(stmt.body, allow_return=False)
        elif isinstance(stmt, ast.For):
            self._validate_for(stmt)
            self._validate_block(stmt.body, allow_return=False)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            self._validate_call(stmt.value)
        else:
            self._reject(
                stmt,
                f"statement of kind '{type(stmt).__name__}' is not supported in this milestone",
            )

    def _validate_for(self, node: ast.For) -> None:
        if node.orelse:
            self._reject(node, "'for ... else' is not supported")
        if not isinstance(node.target, ast.Name):
            self._reject(node.target, "the loop variable must be a plain name")
        if not (
            isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
        ):
            self._reject(node.iter, "'for' is only supported over 'range(...)' in this milestone")
            return
        range_call = node.iter
        if range_call.keywords or not (1 <= len(range_call.args) <= 3):
            self._reject(range_call, "'range' takes 1 to 3 positional arguments")
            return
        for i, arg in enumerate(range_call.args):
            self._validate_expr(arg)
            if i == 2 and extract_int_literal(arg) is None:
                self._reject(
                    arg,
                    "'range' step must be a literal integer constant in this milestone",
                    help_text="a runtime-computed step arrives in a later milestone",
                )

    def _validate_fstring(self, node: ast.JoinedStr) -> None:
        for value in node.values:
            if isinstance(value, ast.Constant):
                continue
            if isinstance(value, ast.FormattedValue):
                if value.conversion != -1:
                    self._reject(
                        value,
                        "f-string conversions ('!r', '!s', '!a') are not supported "
                        "in this milestone",
                    )
                if value.format_spec is not None:
                    self._reject(
                        value.format_spec,
                        "f-string format specs are not supported in this milestone",
                    )
                self._validate_expr(value.value)
            else:
                self._reject(value, "unsupported f-string component")  # pragma: no cover

    def _validate_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            self._reject(node, "only calls to a plain function name are supported")
            return
        if node.keywords:
            self._reject(node, "keyword arguments are not supported")
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                self._reject(arg, "*args-style call arguments are not supported")
            else:
                self._validate_expr(arg)

    def _validate_expr(self, node: ast.expr) -> None:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, str)):
                self._reject(
                    node, "only integer and string literals are supported in this milestone"
                )
        elif isinstance(node, ast.JoinedStr):
            self._validate_fstring(node)
        elif isinstance(node, ast.Name):
            pass
        elif isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_BINOPS):
                self._reject(
                    node, f"operator '{type(node.op).__name__}' is not supported in this milestone"
                )
            self._validate_expr(node.left)
            self._validate_expr(node.right)
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                self._reject(
                    node,
                    "chained comparisons (e.g. 'a < b < c') are not supported in this milestone",
                    help_text="write it as 'a < b and b < c'",
                )
                return
            if not isinstance(node.ops[0], _ALLOWED_COMPARE_OPS):
                self._reject(
                    node,
                    f"comparison '{type(node.ops[0]).__name__}' is not supported in this milestone",
                )
            self._validate_expr(node.left)
            self._validate_expr(node.comparators[0])
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                self._validate_expr(value)
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                if extract_int_literal(node) is None:
                    self._reject(
                        node,
                        "unary '-' is only supported on integer literals in this milestone",
                        help_text="negating an arbitrary expression arrives in a later milestone",
                    )
            elif isinstance(node.op, ast.Not):
                self._validate_expr(node.operand)
            else:
                self._reject(
                    node,
                    f"unary operator '{type(node.op).__name__}' is not supported in this milestone",
                )
        elif isinstance(node, ast.Call):
            self._validate_call(node)
        else:
            self._reject(
                node,
                f"expression of kind '{type(node).__name__}' is not supported in this milestone",
            )
