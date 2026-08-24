"""Structural subset validation.

This pass answers only "is this syntax shape permitted by the v1 subset",
independent of what any name resolves to or what type anything has. Name
resolution and type checking happen later (see semantic/collect.py and
ir/lower.py) and can assume the tree already satisfies these shape rules.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.loader import SourceFile

_ALLOWED_BINOPS: tuple[type[ast.operator], ...] = (ast.Add, ast.Sub, ast.Mult)


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
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                self._validate_call(stmt.value)
            else:
                self._reject(
                    stmt,
                    f"top-level '{type(stmt).__name__}' statements are not supported",
                    help_text=(
                        "module-level code must be a function definition or a call "
                        "statement, e.g. print(...)"
                    ),
                )

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

        if len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
            self._reject(
                node,
                "function bodies must consist of exactly one 'return' statement in this milestone",
                help_text="local variables and control flow arrive in a later milestone",
            )
            return

        return_stmt = node.body[0]
        assert isinstance(return_stmt, ast.Return)
        if return_stmt.value is None:
            self._reject(return_stmt, "'return' must return a value")
            return
        self._validate_expr(return_stmt.value)

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
            if not isinstance(node.value, int) or isinstance(node.value, bool):
                self._reject(node, "only integer literals are supported in this milestone")
        elif isinstance(node, ast.Name):
            pass
        elif isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_BINOPS):
                self._reject(
                    node, f"operator '{type(node.op).__name__}' is not supported in this milestone"
                )
            self._validate_expr(node.left)
            self._validate_expr(node.right)
        elif isinstance(node, ast.Call):
            self._validate_call(node)
        else:
            self._reject(
                node,
                f"expression of kind '{type(node).__name__}' is not supported in this milestone",
            )
