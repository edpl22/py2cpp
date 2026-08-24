"""Resolves a Python type annotation AST node into a py2cpp internal Type.

Shared between function signature collection (semantic/collect.py) and
local variable annotations (ir/lower.py) so both go through one supported
type registry.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.loader import SourceFile
from py2cpp.types.model import BoolType, IntType, StringType, Type

_SUPPORTED_ANNOTATIONS: dict[str, Type] = {
    "int": IntType(),
    "bool": BoolType(),
    "str": StringType(),
}


def resolve_annotation(
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
                "py2cpp does not infer types across a function boundary; annotate it, e.g. 'x: int'"
            ),
        )
        return None

    location = SourceLocation(
        filename=source.path,
        line=getattr(node, "lineno", fallback_location.line),
        column=getattr(node, "col_offset", fallback_location.column - 1) + 1,
    )
    if isinstance(node, ast.Name) and node.id in _SUPPORTED_ANNOTATIONS:
        return _SUPPORTED_ANNOTATIONS[node.id]

    diagnostics.error(
        codes.MISSING_ANNOTATION,
        f"{what} has an unsupported type annotation",
        location,
        help_text="supported types in this milestone: int, bool, str",
    )
    return None
