from __future__ import annotations

from py2cpp.types.model import BoolType, DictType, IntType, ListType, SetType, StringType, TupleType


def test_int_type_equality_and_str() -> None:
    assert IntType() == IntType()
    assert str(IntType()) == "int"


def test_string_type_equality_and_str() -> None:
    assert StringType() == StringType()
    assert str(StringType()) == "str"


def test_list_type_equality_and_str() -> None:
    assert ListType(IntType()) == ListType(IntType())
    assert ListType(IntType()) != ListType(StringType())
    assert str(ListType(IntType())) == "list[int]"


def test_dict_type_equality_and_str() -> None:
    assert DictType(StringType(), IntType()) == DictType(StringType(), IntType())
    assert DictType(StringType(), IntType()) != DictType(IntType(), IntType())
    assert str(DictType(StringType(), IntType())) == "dict[str, int]"


def test_set_type_equality_and_str() -> None:
    assert SetType(IntType()) == SetType(IntType())
    assert str(SetType(IntType())) == "set[int]"


def test_tuple_type_equality_and_str() -> None:
    assert TupleType((IntType(), StringType())) == TupleType((IntType(), StringType()))
    assert TupleType((IntType(), StringType())) != TupleType((StringType(), IntType()))
    assert str(TupleType((IntType(), BoolType()))) == "tuple[int, bool]"
