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
from py2cpp.types.model import (
    BoolType,
    ClassType,
    DictType,
    IntType,
    ListType,
    SetType,
    StringType,
    TupleType,
    Type,
)

_SUPPORTED_ANNOTATIONS: dict[str, Type] = {
    "int": IntType(),
    "bool": BoolType(),
    "str": StringType(),
}
_CONTAINER_ANNOTATIONS = frozenset({"list", "dict", "set", "tuple"})


def resolve_annotation(
    node: ast.expr | None,
    fallback_location: SourceLocation,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    what: str,
    known_classes: frozenset[str],
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

    if isinstance(node, ast.Name) and node.id in known_classes:
        return ClassType(node.id)

    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in _CONTAINER_ANNOTATIONS
    ):
        return _resolve_container_annotation(
            node, location, source, diagnostics, what=what, known_classes=known_classes
        )

    diagnostics.error(
        codes.MISSING_ANNOTATION,
        f"{what} has an unsupported type annotation",
        location,
        help_text=(
            "supported types in this milestone: int, bool, str, "
            "list[T], dict[K, V], set[T], tuple[T, ...], or a class name"
        ),
    )
    return None


def _resolve_container_annotation(
    node: ast.Subscript,
    location: SourceLocation,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    what: str,
    known_classes: frozenset[str],
) -> Type | None:
    assert isinstance(node.value, ast.Name)
    container = node.value.id

    if container == "list":
        element = resolve_annotation(
            node.slice,
            location,
            source,
            diagnostics,
            what=f"{what}'s element type",
            known_classes=known_classes,
        )
        return ListType(element) if element is not None else None

    if container == "set":
        element = resolve_annotation(
            node.slice,
            location,
            source,
            diagnostics,
            what=f"{what}'s element type",
            known_classes=known_classes,
        )
        return SetType(element) if element is not None else None

    if container == "dict":
        if not (isinstance(node.slice, ast.Tuple) and len(node.slice.elts) == 2):
            diagnostics.error(
                codes.MISSING_ANNOTATION,
                f"{what} must be written as 'dict[KeyType, ValueType]'",
                location,
            )
            return None
        key = resolve_annotation(
            node.slice.elts[0],
            location,
            source,
            diagnostics,
            what=f"{what}'s key type",
            known_classes=known_classes,
        )
        value = resolve_annotation(
            node.slice.elts[1],
            location,
            source,
            diagnostics,
            what=f"{what}'s value type",
            known_classes=known_classes,
        )
        return DictType(key, value) if key is not None and value is not None else None

    assert container == "tuple"
    element_nodes = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    element_types: list[Type] = []
    for element_node in element_nodes:
        element = resolve_annotation(
            element_node,
            location,
            source,
            diagnostics,
            what=f"{what}'s element type",
            known_classes=known_classes,
        )
        if element is None:
            return None
        element_types.append(element)
    return TupleType(tuple(element_types))
