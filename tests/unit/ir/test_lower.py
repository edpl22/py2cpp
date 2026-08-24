"""Unit tests for the combined name-resolution / type-check / IR-construction
lowering pass. Uses the full frontend+semantic front half (parse, subset
validate, collect symbols) as fixtures, since lower_module's contract
assumes a tree that already passed those stages.
"""

from __future__ import annotations

import ast
from pathlib import Path

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine
from py2cpp.frontend.loader import SourceFile
from py2cpp.ir.lower import lower_module
from py2cpp.ir.nodes import IRBinaryExpr, IRCall, IRModule, IRPrintStmt, IRReturn
from py2cpp.semantic.collect import collect_symbols

_PATH = Path("test.py")


def _lower(text: str) -> tuple[DiagnosticEngine, IRModule | None]:
    tree = ast.parse(text, filename=str(_PATH))
    source = SourceFile(path=_PATH, text=text)
    diagnostics = DiagnosticEngine()
    symtab = collect_symbols(tree, source, diagnostics)
    module = lower_module(tree, symtab, source, diagnostics)
    return diagnostics, module


def test_lowers_add_example() -> None:
    diagnostics, module = _lower(
        "def add(a: int, b: int) -> int:\n    return a + b\n\n\nprint(add(2, 3))\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    assert len(module.functions) == 1
    function = module.functions[0]
    assert function.name == "add"
    return_stmt = function.body[0]
    assert isinstance(return_stmt, IRReturn)
    assert isinstance(return_stmt.value, IRBinaryExpr)

    assert len(module.main_body) == 1
    print_stmt = module.main_body[0]
    assert isinstance(print_stmt, IRPrintStmt)
    assert isinstance(print_stmt.args[0], IRCall)
    assert print_stmt.args[0].callee == "add"


def test_call_across_functions_is_allowed_regardless_of_source_order() -> None:
    # `sum_of_squares` calls `square`, which is defined *after* it in the
    # source -- allowed, because a function body only runs once the whole
    # module (including every def) has finished loading.
    diagnostics, module = _lower(
        "def sum_of_squares(a: int, b: int) -> int:\n"
        "    return square(a)\n"
        "\n\n"
        "def square(x: int) -> int:\n"
        "    return x * x\n"
    )
    assert not diagnostics.has_errors
    assert module is not None


def test_top_level_call_before_definition_is_rejected() -> None:
    diagnostics, module = _lower(
        "print(add(1, 2))\n"
        "\n\n"
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.UNDEFINED_NAME


def test_wrong_argument_count_is_rejected() -> None:
    diagnostics, module = _lower(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "\n\n"
        "print(add(1, 2, 3))\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.ARGUMENT_COUNT_MISMATCH


def test_integer_literal_out_of_int64_range_is_rejected() -> None:
    diagnostics, module = _lower(
        "def identity(a: int) -> int:\n"
        "    return a\n"
        "\n\n"
        "print(identity(99999999999999999999999999))\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_print_used_as_a_value_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(a: int) -> int:\n    return print(a)\n\n\nf(1)\n"
    )
    assert diagnostics.has_errors
    assert module is None
