from __future__ import annotations

import ast
from pathlib import Path

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine
from py2cpp.frontend.loader import SourceFile
from py2cpp.semantic.collect import collect_symbols
from py2cpp.semantic.symbols import SymbolTable
from py2cpp.types.model import (
    ClassType,
    DictType,
    IntType,
    ListType,
    SetType,
    StringType,
    TupleType,
)

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


def test_collects_class_with_attributes_and_methods() -> None:
    diagnostics, table = _collect(
        "class Point:\n"
        "    def __init__(self, x: int, y: int) -> None:\n"
        "        self.x: int = x\n"
        "        self.y: int = y\n"
        "\n"
        "    def sum(self) -> int:\n"
        "        return self.x + self.y\n"
    )
    assert not diagnostics.has_errors
    point = table.classes["Point"]
    assert point.base is None
    assert [p.name for p in point.init_parameters] == ["x", "y"]
    assert point.attributes["x"].type == IntType()
    assert point.attributes["y"].type == IntType()
    assert point.methods["sum"].return_type == IntType()
    assert point.methods["sum"].parameters == ()


def test_collects_subclass_base_and_own_attributes() -> None:
    diagnostics, table = _collect(
        "class Animal:\n"
        "    def __init__(self, name: str) -> None:\n"
        "        self.name: str = name\n"
        "\n"
        "class Dog(Animal):\n"
        "    def __init__(self, name: str, age: int) -> None:\n"
        "        super().__init__(name)\n"
        "        self.age: int = age\n"
    )
    assert not diagnostics.has_errors
    dog = table.classes["Dog"]
    assert dog.base == "Animal"
    assert "age" in dog.attributes
    assert "name" not in dog.attributes  # inherited, not redeclared


def test_class_without_init_is_reported() -> None:
    diagnostics, _ = _collect("class Foo:\n    def bar(self) -> int:\n        return 1\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.MISSING_ANNOTATION


def test_attribute_referencing_own_class_resolves() -> None:
    diagnostics, table = _collect(
        "class Box:\n"
        "    def __init__(self, item: int) -> None:\n"
        "        self.item: int = item\n"
        "\n"
        "class Wrapper:\n"
        "    def __init__(self, box: Box) -> None:\n"
        "        self.box: Box = box\n"
    )
    assert not diagnostics.has_errors
    assert table.classes["Wrapper"].attributes["box"].type == ClassType("Box")


def test_reassigning_inherited_attribute_with_same_type_is_not_a_duplicate() -> None:
    diagnostics, table = _collect(
        "class Animal:\n"
        "    def __init__(self) -> None:\n"
        "        self.age: int = 0\n"
        "\n"
        "class Dog(Animal):\n"
        "    def __init__(self, age: int) -> None:\n"
        "        super().__init__()\n"
        "        self.age: int = age\n"
    )
    assert not diagnostics.has_errors
    assert "age" not in table.classes["Dog"].attributes


def test_shadowing_inherited_attribute_with_different_type_is_reported() -> None:
    diagnostics, _ = _collect(
        "class Animal:\n"
        "    def __init__(self) -> None:\n"
        "        self.age: int = 0\n"
        "\n"
        "class Dog(Animal):\n"
        "    def __init__(self, age: str) -> None:\n"
        "        super().__init__()\n"
        "        self.age: str = age\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.DUPLICATE_DEFINITION


def test_undefined_base_class_is_reported() -> None:
    diagnostics, _ = _collect(
        "class Dog(Animal):\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__()\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNDEFINED_NAME
