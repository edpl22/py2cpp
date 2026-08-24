"""Recognizes compile-time integer literals, including a negative literal
written as unary minus applied to a Constant (how CPython's parser
actually represents e.g. '-2' -- ast.Constant never holds a negative
int). Shared by the subset validator (to decide whether a 'range' step is
a literal at all) and the lowering pass (to extract its value).
"""

from __future__ import annotations

import ast


def extract_int_literal(node: ast.expr) -> int | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
        and not isinstance(node.operand.value, bool)
    ):
        return -node.operand.value
    return None
