from __future__ import annotations

from py2cpp.types.model import IntType, StringType


def test_int_type_equality_and_str() -> None:
    assert IntType() == IntType()
    assert str(IntType()) == "int"


def test_string_type_equality_and_str() -> None:
    assert StringType() == StringType()
    assert str(StringType()) == "str"
