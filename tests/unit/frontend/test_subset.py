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


def test_accepts_multi_statement_function_body_ending_in_return() -> None:
    diagnostics = _validate("def f(a: int) -> int:\n    x = a\n    return x\n\n\nprint(f(1))\n")
    assert not diagnostics.has_errors


def test_rejects_return_nested_inside_if() -> None:
    diagnostics = _validate(
        "def f(a: int) -> int:\n    if a > 0:\n        return a\n    return 0\n\n\nprint(f(1))\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_chained_comparison() -> None:
    diagnostics = _validate(
        "def f(a: int, b: int, c: int) -> int:\n    if a < b < c:\n        return 1\n    return 0\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_accepts_control_flow() -> None:
    diagnostics = _validate(
        "def f(a: int) -> int:\n"
        "    total: int = 0\n"
        "    for i in range(a):\n"
        "        if i > 2:\n"
        "            total = total + i\n"
        "        else:\n"
        "            total = total - i\n"
        "    while total > 100:\n"
        "        total = total - 1\n"
        "    return total\n"
    )
    assert not diagnostics.has_errors


def test_rejects_range_with_non_literal_step() -> None:
    diagnostics = _validate(
        "def f(a: int, step: int) -> int:\n"
        "    total: int = 0\n"
        "    for i in range(0, a, step):\n"
        "        total = total + i\n"
        "    return total\n"
    )
    assert diagnostics.has_errors


def test_rejects_unsupported_operator() -> None:
    diagnostics = _validate("def f(a: int, b: int) -> int:\n    return a / b\n\n\nprint(f(1, 2))\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_decorators() -> None:
    diagnostics = _validate("@staticmethod\ndef f(a: int) -> int:\n    return a\n\n\nprint(f(1))\n")
    assert diagnostics.has_errors


def test_rejects_keyword_call_arguments() -> None:
    diagnostics = _validate("def f(a: int) -> int:\n    return a\n\n\nprint(f(a=1))\n")
    assert diagnostics.has_errors


def test_accepts_string_literal_and_concatenation() -> None:
    diagnostics = _validate(
        "def greet(name: str) -> str:\n    return 'hello, ' + name\n\n\nprint(greet('world'))\n"
    )
    assert not diagnostics.has_errors


def test_accepts_fstring() -> None:
    diagnostics = _validate(
        "def describe(n: int) -> str:\n    return f'n = {n}'\n\n\nprint(describe(3))\n"
    )
    assert not diagnostics.has_errors


def test_rejects_fstring_conversion() -> None:
    diagnostics = _validate(
        "def describe(n: int) -> str:\n    return f'n = {n!r}'\n\n\nprint(describe(3))\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_fstring_format_spec() -> None:
    diagnostics = _validate(
        "def describe(n: int) -> str:\n    return f'n = {n:04d}'\n\n\nprint(describe(3))\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX
