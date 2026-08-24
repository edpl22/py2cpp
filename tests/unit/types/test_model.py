from __future__ import annotations

from py2cpp.types.model import IntType


def test_int_type_equality_and_str() -> None:
    assert IntType() == IntType()
    assert str(IntType()) == "int"
