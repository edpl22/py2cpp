from __future__ import annotations

from py2cpp.types.join import is_assignable, join
from py2cpp.types.model import BoolType, IntType, StringType


def test_same_type_joins_to_itself() -> None:
    assert join(IntType(), IntType()) == IntType()
    assert join(BoolType(), BoolType()) == BoolType()


def test_bool_widens_to_int_regardless_of_argument_order() -> None:
    assert join(IntType(), BoolType()) == IntType()
    assert join(BoolType(), IntType()) == IntType()


def test_bool_is_assignable_to_int_but_not_the_reverse() -> None:
    assert is_assignable(BoolType(), IntType())
    assert not is_assignable(IntType(), BoolType())


def test_same_type_is_always_assignable() -> None:
    assert is_assignable(IntType(), IntType())
    assert is_assignable(BoolType(), BoolType())


def test_string_joins_only_with_itself() -> None:
    assert join(StringType(), StringType()) == StringType()
    assert join(StringType(), IntType()) is None
    assert join(StringType(), BoolType()) is None
    assert join(IntType(), StringType()) is None
