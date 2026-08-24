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
from py2cpp.ir.nodes import (
    IRAssign,
    IRBinaryExpr,
    IRCall,
    IRFor,
    IRIf,
    IRModule,
    IRPrintStmt,
    IRReturn,
    IRStringLiteral,
    IRToStr,
    IRWhile,
)
from py2cpp.semantic.collect import collect_symbols
from py2cpp.types.model import BoolType, IntType, StringType

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
        "print(add(1, 2))\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.UNDEFINED_NAME


def test_wrong_argument_count_is_rejected() -> None:
    diagnostics, module = _lower(
        "def add(a: int, b: int) -> int:\n    return a + b\n\n\nprint(add(1, 2, 3))\n"
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
    diagnostics, module = _lower("def f(a: int) -> int:\n    return print(a)\n\n\nf(1)\n")
    assert diagnostics.has_errors
    assert module is None


def test_if_elif_else_reassigns_a_variable_pre_declared_before_the_conditional() -> None:
    diagnostics, module = _lower(
        "def classify(n: int) -> int:\n"
        "    result: int = 0\n"
        "    if n < 0:\n"
        "        result = -1\n"
        "    elif n == 0:\n"
        "        result = 0\n"
        "    else:\n"
        "        result = 1\n"
        "    return result\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    function = module.functions[0]
    assign, if_stmt, return_stmt = function.body
    assert isinstance(assign, IRAssign) and assign.declare
    assert isinstance(if_stmt, IRIf)
    # 'elif' lowers to a nested IRIf inside else_body, not a flat chain.
    assert len(if_stmt.else_body) == 1
    assert isinstance(if_stmt.else_body[0], IRIf)
    assert isinstance(return_stmt, IRReturn)
    # every branch reassigns the pre-declared 'result', never redeclaring it.
    then_assign = if_stmt.then_body[0]
    assert isinstance(then_assign, IRAssign) and not then_assign.declare


def test_variable_first_assigned_inside_branch_does_not_survive_the_branch() -> None:
    diagnostics, module = _lower(
        "def f(a: int) -> int:\n    if a > 0:\n        result = a\n    return result\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.UNDEFINED_NAME


def test_reassigning_bool_established_variable_to_int_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(a: int, b: int) -> int:\n    flag = a < b\n    flag = a + b\n    return flag\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_bool_operand_widens_to_int_in_arithmetic() -> None:
    diagnostics, module = _lower(
        "def f(a: int, b: int) -> int:\n"
        "    count: int = 0\n"
        "    count = count + (a > b)\n"
        "    return count\n"
    )
    assert not diagnostics.has_errors
    assert module is not None


def test_while_loop_lowers() -> None:
    diagnostics, module = _lower(
        "def f(n: int) -> int:\n"
        "    total: int = 0\n"
        "    i: int = 0\n"
        "    while i < n:\n"
        "        total = total + i\n"
        "        i = i + 1\n"
        "    return total\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    function = module.functions[0]
    while_stmt = function.body[2]
    assert isinstance(while_stmt, IRWhile)
    assert isinstance(while_stmt.condition.type, BoolType)


def test_for_range_lowers_loop_variable_as_int() -> None:
    diagnostics, module = _lower(
        "def f(n: int) -> int:\n"
        "    total: int = 0\n"
        "    for i in range(n):\n"
        "        total = total + i\n"
        "    return total\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    function = module.functions[0]
    for_stmt = function.body[1]
    assert isinstance(for_stmt, IRFor)
    assert for_stmt.step == 1
    assert isinstance(for_stmt.start.type, IntType)


def test_for_range_with_negative_literal_step() -> None:
    diagnostics, module = _lower(
        "def f() -> int:\n"
        "    total: int = 0\n"
        "    for i in range(10, 0, -2):\n"
        "        total = total + i\n"
        "    return total\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    function = module.functions[0]
    for_stmt = function.body[1]
    assert isinstance(for_stmt, IRFor)
    assert for_stmt.step == -2


def test_print_accepts_bool_argument() -> None:
    diagnostics, module = _lower(
        "def f(a: int, b: int) -> bool:\n    return a < b\n\n\nprint(f(1, 2))\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    print_stmt = module.main_body[0]
    assert isinstance(print_stmt, IRPrintStmt)


def test_string_literal_and_concatenation_lower() -> None:
    diagnostics, module = _lower(
        "def greet(name: str) -> str:\n    return 'hello, ' + name\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    return_stmt = module.functions[0].body[0]
    assert isinstance(return_stmt, IRReturn)
    value = return_stmt.value
    assert isinstance(value, IRBinaryExpr)
    assert isinstance(value.type, StringType)
    assert isinstance(value.left, IRStringLiteral)
    assert value.left.value == "hello, "


def test_string_minus_string_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(a: str, b: str) -> str:\n    return a - b\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_string_plus_int_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(a: str, b: int) -> str:\n    return a + b\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_fstring_lowers_literal_parts_and_wraps_non_string_values() -> None:
    diagnostics, module = _lower(
        "def describe(n: int) -> str:\n    return f'n = {n}!'\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    return_stmt = module.functions[0].body[0]
    assert isinstance(return_stmt, IRReturn)
    # f'n = {n}!' folds to ("n = " + str(n)) + "!"
    outer = return_stmt.value
    assert isinstance(outer, IRBinaryExpr)
    assert isinstance(outer.type, StringType)
    assert isinstance(outer.right, IRStringLiteral)
    assert outer.right.value == "!"
    inner = outer.left
    assert isinstance(inner, IRBinaryExpr)
    assert isinstance(inner.left, IRStringLiteral)
    assert inner.left.value == "n = "
    assert isinstance(inner.right, IRToStr)


def test_fstring_rejects_unsupported_value_type() -> None:
    diagnostics, module = _lower(
        "def f(a: int) -> str:\n    return f'{print}'\n\n\nf(1)\n"
    )
    assert diagnostics.has_errors
    assert module is None


def test_print_accepts_string_argument() -> None:
    diagnostics, module = _lower("print('hello')\n")
    assert not diagnostics.has_errors
    assert module is not None
    print_stmt = module.main_body[0]
    assert isinstance(print_stmt, IRPrintStmt)
    assert isinstance(print_stmt.args[0], IRStringLiteral)
