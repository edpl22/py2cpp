from __future__ import annotations

import ast
from pathlib import Path

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine
from py2cpp.frontend.loader import SourceFile
from py2cpp.semantic.collect import collect_symbols
from py2cpp.semantic.symbols import SymbolTable
from py2cpp.types.model import DictType, IntType, ListType, SetType, StringType, TupleType

_PATH = Path("test.py")


def _collect(text: str) -> tuple[DiagnosticEngine, SymbolTable]:
    tree = ast.parse(text, filename=str(_PATH))
    diagnostics = DiagnosticEngine()
    table = collect_symbols(tree, SourceFile(path=_PATH, text=text), diagnostics)
    return diagnostics, table


def test_collects_function_signature() -> None:
    diagnostics, table = _collect("def add(a: int, b: int) -> int:\n    return a + b\n")
    assert not diagnostics.has_errors
    symbol = table.functions["add"]
    assert [p.name for p in symbol.parameters] == ["a", "b"]
    assert all(p.type == IntType() for p in symbol.parameters)
    assert symbol.return_type == IntType()


def test_missing_parameter_annotation_is_reported() -> None:
    diagnostics, _ = _collect("def add(a, b: int) -> int:\n    return a + b\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.MISSING_ANNOTATION


def test_missing_return_annotation_is_reported() -> None:
    diagnostics, _ = _collect("def add(a: int, b: int):\n    return a + b\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.MISSING_ANNOTATION


def test_collects_string_parameter_and_return_type() -> None:
    diagnostics, table = _collect("def greet(name: str) -> str:\n    return name\n")
    assert not diagnostics.has_errors
    symbol = table.functions["greet"]
    assert symbol.parameters[0].type == StringType()
    assert symbol.return_type == StringType()


def test_collects_list_parameter_type() -> None:
    diagnostics, table = _collect("def first(values: list[int]) -> int:\n    return 0\n")
    assert not diagnostics.has_errors
    assert table.functions["first"].parameters[0].type == ListType(IntType())


def test_collects_dict_parameter_type() -> None:
    diagnostics, table = _collect("def f(ages: dict[str, int]) -> int:\n    return 0\n")
    assert not diagnostics.has_errors
    assert table.functions["f"].parameters[0].type == DictType(StringType(), IntType())


def test_collects_set_parameter_type() -> None:
    diagnostics, table = _collect("def f(values: set[int]) -> int:\n    return 0\n")
    assert not diagnostics.has_errors
    assert table.functions["f"].parameters[0].type == SetType(IntType())


def test_collects_tuple_parameter_type() -> None:
    diagnostics, table = _collect("def f(pair: tuple[int, str]) -> int:\n    return 0\n")
    assert not diagnostics.has_errors
    assert table.functions["f"].parameters[0].type == TupleType((IntType(), StringType()))


def test_collects_nested_container_type() -> None:
    diagnostics, table = _collect("def f(rows: list[list[int]]) -> int:\n    return 0\n")
    assert not diagnostics.has_errors
    assert table.functions["f"].parameters[0].type == ListType(ListType(IntType()))


def test_dict_annotation_without_two_arguments_is_rejected() -> None:
    diagnostics, _ = _collect("def f(ages: dict[str]) -> int:\n    return 0\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.MISSING_ANNOTATION


def test_duplicate_function_definition_is_reported() -> None:
    diagnostics, table = _collect(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "\n\n"
        "def add(a: int, b: int) -> int:\n"
        "    return a - b\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.DUPLICATE_DEFINITION
    assert table.functions["add"].location.line == 1
