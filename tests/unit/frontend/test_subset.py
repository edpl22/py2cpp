from __future__ import annotations

import ast
from pathlib import Path

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine
from py2cpp.frontend.loader import SourceFile
from py2cpp.frontend.subset import validate_subset

_PATH = Path("test.py")


def _validate(text: str) -> DiagnosticEngine:
    tree = ast.parse(text, filename=str(_PATH))
    diagnostics = DiagnosticEngine()
    validate_subset(tree, SourceFile(path=_PATH, text=text), diagnostics)
    return diagnostics


def test_accepts_the_add_example() -> None:
    diagnostics = _validate(
        "def add(a: int, b: int) -> int:\n    return a + b\n\n\nprint(add(2, 3))\n"
    )
    assert not diagnostics.has_errors


def test_rejects_class_definitions() -> None:
    diagnostics = _validate("class Foo:\n    pass\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_multi_statement_function_body() -> None:
    diagnostics = _validate(
        "def f(a: int) -> int:\n    x = a\n    return x\n\n\nprint(f(1))\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_unsupported_operator() -> None:
    diagnostics = _validate("def f(a: int, b: int) -> int:\n    return a / b\n\n\nprint(f(1, 2))\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_decorators() -> None:
    diagnostics = _validate(
        "@staticmethod\ndef f(a: int) -> int:\n    return a\n\n\nprint(f(1))\n"
    )
    assert diagnostics.has_errors


def test_rejects_keyword_call_arguments() -> None:
    diagnostics = _validate(
        "def f(a: int) -> int:\n    return a\n\n\nprint(f(a=1))\n"
    )
    assert diagnostics.has_errors
