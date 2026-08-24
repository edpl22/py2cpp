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
    IRDictLiteral,
    IRFor,
    IRForEach,
    IRIf,
    IRIndex,
    IRListCompForEach,
    IRListCompRange,
    IRListLiteral,
    IRModule,
    IRPrintStmt,
    IRReturn,
    IRSetLiteral,
    IRStringLiteral,
    IRToStr,
    IRTupleIndex,
    IRTupleLiteral,
    IRWhile,
)
from py2cpp.semantic.collect import collect_symbols
from py2cpp.types.model import (
    BoolType,
    DictType,
    IntType,
    ListType,
    SetType,
    StringType,
    TupleType,
)

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


def test_list_literal_infers_homogeneous_element_type() -> None:
    diagnostics, module = _lower("values = [1, 2, 3]\nprint(values)\n")
    assert not diagnostics.has_errors
    assert module is not None
    assign = module.main_body[0]
    assert isinstance(assign, IRAssign)
    assert isinstance(assign.value, IRListLiteral)
    assert assign.type == ListType(IntType())


def test_list_literal_widens_bool_and_int_elements() -> None:
    diagnostics, module = _lower("values = [1, (2 > 1), 3]\nprint(values)\n")
    assert not diagnostics.has_errors
    assert module is not None
    assign = module.main_body[0]
    assert isinstance(assign, IRAssign)
    assert assign.type == ListType(IntType())


def test_list_literal_with_incompatible_element_types_is_rejected() -> None:
    diagnostics, module = _lower("values = [1, 'a']\nprint(values)\n")
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_dict_literal_infers_key_and_value_types() -> None:
    diagnostics, module = _lower("ages = {'alice': 30, 'bob': 25}\nprint(ages)\n")
    assert not diagnostics.has_errors
    assert module is not None
    assign = module.main_body[0]
    assert isinstance(assign, IRAssign)
    assert isinstance(assign.value, IRDictLiteral)
    assert assign.type == DictType(StringType(), IntType())


def test_set_literal_infers_element_type() -> None:
    diagnostics, module = _lower("values = {1, 2, 3}\nprint(values)\n")
    assert not diagnostics.has_errors
    assert module is not None
    assign = module.main_body[0]
    assert isinstance(assign, IRAssign)
    assert isinstance(assign.value, IRSetLiteral)
    assert assign.type == SetType(IntType())


def test_tuple_literal_keeps_heterogeneous_element_types() -> None:
    diagnostics, module = _lower("pair = (1, 'a')\nprint(pair)\n")
    assert not diagnostics.has_errors
    assert module is not None
    assign = module.main_body[0]
    assert isinstance(assign, IRAssign)
    assert isinstance(assign.value, IRTupleLiteral)
    assert assign.type == TupleType((IntType(), StringType()))


def test_list_index_lowers_to_ir_index() -> None:
    diagnostics, module = _lower(
        "def first(values: list[int]) -> int:\n    return values[0]\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    return_stmt = module.functions[0].body[0]
    assert isinstance(return_stmt, IRReturn)
    assert isinstance(return_stmt.value, IRIndex)
    assert return_stmt.value.type == IntType()


def test_dict_index_requires_matching_key_type() -> None:
    diagnostics, module = _lower(
        "def f(ages: dict[str, int]) -> int:\n    return ages[1]\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_tuple_index_with_literal_lowers_to_ir_tuple_index() -> None:
    diagnostics, module = _lower(
        "def f(pair: tuple[int, str]) -> str:\n    return pair[1]\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    return_stmt = module.functions[0].body[0]
    assert isinstance(return_stmt, IRReturn)
    assert isinstance(return_stmt.value, IRTupleIndex)
    assert return_stmt.value.index == 1
    assert return_stmt.value.type == StringType()


def test_tuple_index_with_negative_literal_resolves_position() -> None:
    diagnostics, module = _lower(
        "def f(pair: tuple[int, str]) -> str:\n    return pair[-1]\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    return_stmt = module.functions[0].body[0]
    assert isinstance(return_stmt, IRReturn)
    assert isinstance(return_stmt.value, IRTupleIndex)
    assert return_stmt.value.index == 1


def test_tuple_index_with_variable_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(pair: tuple[int, str], i: int) -> str:\n    return pair[i]\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_tuple_index_out_of_range_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(pair: tuple[int, str]) -> str:\n    return pair[5]\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_set_indexing_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(values: set[int]) -> int:\n    return values[0]\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_for_each_over_list_lowers_element_type() -> None:
    diagnostics, module = _lower(
        "def total_of(values: list[int]) -> int:\n"
        "    total: int = 0\n"
        "    for v in values:\n"
        "        total = total + v\n"
        "    return total\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    for_stmt = module.functions[0].body[1]
    assert isinstance(for_stmt, IRForEach)
    assert for_stmt.var_type == IntType()


def test_for_each_over_dict_binds_key_type() -> None:
    diagnostics, module = _lower(
        "def f(ages: dict[str, int]) -> int:\n"
        "    total: int = 0\n"
        "    for name in ages:\n"
        "        total = total + ages[name]\n"
        "    return total\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    for_stmt = module.functions[0].body[1]
    assert isinstance(for_stmt, IRForEach)
    assert for_stmt.var_type == StringType()


def test_iterating_a_tuple_is_rejected() -> None:
    diagnostics, module = _lower(
        "def f(pair: tuple[int, int]) -> int:\n"
        "    total: int = 0\n"
        "    for v in pair:\n"
        "        total = total + v\n"
        "    return total\n"
    )
    assert diagnostics.has_errors
    assert module is None
    assert diagnostics.diagnostics[0].code == codes.TYPE_MISMATCH


def test_list_comprehension_over_range_lowers() -> None:
    diagnostics, module = _lower("squares = [x * x for x in range(5)]\nprint(squares)\n")
    assert not diagnostics.has_errors
    assert module is not None
    assign = module.main_body[0]
    assert isinstance(assign, IRAssign)
    assert isinstance(assign.value, IRListCompRange)
    assert assign.type == ListType(IntType())


def test_list_comprehension_over_container_with_condition_lowers() -> None:
    diagnostics, module = _lower(
        "def positives(values: list[int]) -> list[int]:\n"
        "    return [x for x in values if x > 0]\n"
    )
    assert not diagnostics.has_errors
    assert module is not None
    return_stmt = module.functions[0].body[0]
    assert isinstance(return_stmt, IRReturn)
    assert isinstance(return_stmt.value, IRListCompForEach)
    assert return_stmt.value.condition is not None


def test_print_accepts_list_argument() -> None:
    diagnostics, module = _lower("print([1, 2, 3])\n")
    assert not diagnostics.has_errors
    assert module is not None
