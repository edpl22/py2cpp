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


def test_rejects_class_without_init() -> None:
    diagnostics = _validate("class Foo:\n    pass\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_accepts_well_formed_class() -> None:
    diagnostics = _validate(
        "class Point:\n"
        "    def __init__(self, x: int, y: int) -> None:\n"
        "        self.x: int = x\n"
        "        self.y: int = y\n"
        "\n"
        "    def sum(self) -> int:\n"
        "        return self.x + self.y\n"
    )
    assert not diagnostics.has_errors


def test_accepts_subclass_with_super_init() -> None:
    diagnostics = _validate(
        "class Animal:\n"
        "    def __init__(self, name: str) -> None:\n"
        "        self.name: str = name\n"
        "\n"
        "class Dog(Animal):\n"
        "    def __init__(self, name: str) -> None:\n"
        "        super().__init__(name)\n"
    )
    assert not diagnostics.has_errors


def test_rejects_subclass_missing_super_init() -> None:
    diagnostics = _validate(
        "class Animal:\n"
        "    def __init__(self, name: str) -> None:\n"
        "        self.name: str = name\n"
        "\n"
        "class Dog(Animal):\n"
        "    def __init__(self, name: str) -> None:\n"
        "        pass\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_multiple_inheritance() -> None:
    diagnostics = _validate(
        "class A:\n"
        "    def __init__(self) -> None:\n"
        "        pass\n"
        "\n"
        "class B:\n"
        "    def __init__(self) -> None:\n"
        "        pass\n"
        "\n"
        "class C(A, B):\n"
        "    def __init__(self) -> None:\n"
        "        pass\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_attribute_declared_inside_branch() -> None:
    diagnostics = _validate(
        "class Foo:\n"
        "    def __init__(self, cond: bool) -> None:\n"
        "        if cond:\n"
        "            self.x: int = 1\n"
        "        else:\n"
        "            self.x: int = 2\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_self_used_as_a_value() -> None:
    diagnostics = _validate(
        "class Foo:\n"
        "    def __init__(self) -> None:\n"
        "        pass\n"
        "\n"
        "    def get(self) -> Foo:\n"
        "        return self\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_accepts_attribute_mutation_from_outside() -> None:
    diagnostics = _validate(
        "class Foo:\n"
        "    def __init__(self, x: int) -> None:\n"
        "        self.x: int = x\n"
        "\n"
        "foo = Foo(1)\n"
        "foo.x = 2\n"
    )
    assert not diagnostics.has_errors


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


def test_accepts_list_dict_set_tuple_literals() -> None:
    diagnostics = _validate(
        "def f() -> int:\n"
        "    a: list[int] = [1, 2, 3]\n"
        "    b: dict[str, int] = {'x': 1}\n"
        "    c: set[int] = {1, 2}\n"
        "    d: tuple[int, int] = (1, 2)\n"
        "    return a[0]\n"
    )
    assert not diagnostics.has_errors


def test_rejects_empty_list_literal() -> None:
    diagnostics = _validate("def f() -> int:\n    a = []\n    return 0\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_empty_dict_literal() -> None:
    diagnostics = _validate("def f() -> int:\n    a = {}\n    return 0\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_accepts_indexing() -> None:
    diagnostics = _validate(
        "def f(values: list[int]) -> int:\n    return values[0]\n\n\nprint(f([1]))\n"
    )
    assert not diagnostics.has_errors


def test_accepts_for_over_container() -> None:
    diagnostics = _validate(
        "def f(values: list[int]) -> int:\n"
        "    total: int = 0\n"
        "    for v in values:\n"
        "        total = total + v\n"
        "    return total\n"
    )
    assert not diagnostics.has_errors


def test_accepts_list_comprehension_with_condition() -> None:
    diagnostics = _validate(
        "def f(values: list[int]) -> list[int]:\n"
        "    return [x * 2 for x in values if x > 0]\n"
    )
    assert not diagnostics.has_errors


def test_rejects_comprehension_with_multiple_for_clauses() -> None:
    diagnostics = _validate(
        "def f(values: list[int], more: list[int]) -> list[int]:\n"
        "    return [x for x in values for y in more]\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_accepts_try_except_with_binding() -> None:
    diagnostics = _validate(
        "def f(a: int, b: int) -> int:\n"
        "    result: int = 0\n"
        "    try:\n"
        "        result = a // b\n"
        "    except ZeroDivisionError as e:\n"
        "        print(e)\n"
        "    return result\n"
    )
    assert not diagnostics.has_errors


def test_accepts_bare_except() -> None:
    diagnostics = _validate(
        "def f() -> int:\n"
        "    try:\n"
        "        raise ValueError('x')\n"
        "    except:\n"
        "        pass\n"
        "    return 0\n"
    )
    assert not diagnostics.has_errors


def test_rejects_try_else() -> None:
    diagnostics = _validate(
        "def f() -> int:\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError:\n"
        "        pass\n"
        "    else:\n"
        "        pass\n"
        "    return 0\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_finally() -> None:
    diagnostics = _validate(
        "def f() -> int:\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError:\n"
        "        pass\n"
        "    finally:\n"
        "        pass\n"
        "    return 0\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_multiple_exception_types_in_one_except() -> None:
    diagnostics = _validate(
        "def f() -> int:\n"
        "    try:\n"
        "        pass\n"
        "    except (ValueError, TypeError):\n"
        "        pass\n"
        "    return 0\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_accepts_bare_reraise_inside_except() -> None:
    diagnostics = _validate(
        "def f() -> int:\n"
        "    try:\n"
        "        raise ValueError('x')\n"
        "    except ValueError:\n"
        "        raise\n"
        "    return 0\n"
    )
    assert not diagnostics.has_errors


def test_rejects_bare_reraise_outside_except() -> None:
    diagnostics = _validate("def f() -> int:\n    raise\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_raise_from() -> None:
    diagnostics = _validate(
        "def f() -> int:\n"
        "    try:\n"
        "        raise ValueError('x') from None\n"
        "    except ValueError:\n"
        "        pass\n"
        "    return 0\n"
    )
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_rejects_raise_of_bare_name() -> None:
    diagnostics = _validate("def f() -> int:\n    raise ValueError\n")
    assert diagnostics.has_errors
    assert diagnostics.diagnostics[0].code == codes.UNSUPPORTED_SYNTAX


def test_accepts_floor_division() -> None:
    diagnostics = _validate("def f(a: int, b: int) -> int:\n    return a // b\n")
    assert not diagnostics.has_errors
