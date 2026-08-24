"""Builds the module symbol table from function definitions, resolving
each parameter's and return value's type annotation along the way.

Symbol-table construction is kept separate from expression-level name
resolution and type checking (see ir/lower.py): the table it produces is a
shared artifact both that pass and the backend rely on.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.loader import SourceFile
from py2cpp.semantic.symbols import FunctionSymbol, ParameterSymbol, SymbolTable
from py2cpp.types.model import IntType, Type

_SUPPORTED_ANNOTATIONS: dict[str, Type] = {"int": IntType()}


def collect_symbols(
    tree: ast.Module, source: SourceFile, diagnostics: DiagnosticEngine
) -> SymbolTable:
    table = SymbolTable()
    for stmt in tree.body:
        if not isinstance(stmt, ast.FunctionDef):
            continue
        symbol = _collect_function(stmt, source, diagnostics)
        if symbol is None:
            continue
        existing = table.functions.get(symbol.name)
        if existing is not None:
            diagnostics.error(
                codes.DUPLICATE_DEFINITION,
                f"function '{symbol.name}' is already defined",
                symbol.location,
                help_text=f"the previous definition is at {existing.location}",
            )
            continue
        table.functions[symbol.name] = symbol
    return table


def _location(source: SourceFile, node: ast.AST) -> SourceLocation:
    return SourceLocation(
        filename=source.path,
        line=getattr(node, "lineno", 1),
        column=getattr(node, "col_offset", 0) + 1,
    )


def _resolve_annotation(
    node: ast.expr | None,
    fallback_location: SourceLocation,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    what: str,
) -> Type | None:
    if node is None:
        diagnostics.error(
            codes.MISSING_ANNOTATION,
            f"{what} requires an explicit type annotation",
            fallback_location,
            help_text=(
                "py2cpp does not infer types across a function boundary; "
                "annotate it, e.g. 'x: int'"
            ),
        )
        return None

    location = _location(source, node)
    if isinstance(node, ast.Name) and node.id in _SUPPORTED_ANNOTATIONS:
        return _SUPPORTED_ANNOTATIONS[node.id]

    diagnostics.error(
        codes.MISSING_ANNOTATION,
        f"{what} has an unsupported type annotation",
        location,
        help_text="supported types in this milestone: int",
    )
    return None


def _collect_function(
    node: ast.FunctionDef, source: SourceFile, diagnostics: DiagnosticEngine
) -> FunctionSymbol | None:
    location = _location(source, node)
    ok = True

    parameters: list[ParameterSymbol] = []
    for arg in node.args.args:
        arg_location = _location(source, arg)
        arg_type = _resolve_annotation(
            arg.annotation, arg_location, source, diagnostics, what=f"parameter '{arg.arg}'"
        )
        if arg_type is None:
            ok = False
            continue
        parameters.append(ParameterSymbol(name=arg.arg, type=arg_type, location=arg_location))

    return_type = _resolve_annotation(
        node.returns, location, source, diagnostics, what=f"function '{node.name}'s return value"
    )

    if not ok or return_type is None:
        return None
    return FunctionSymbol(
        name=node.name, parameters=tuple(parameters), return_type=return_type, location=location
    )
