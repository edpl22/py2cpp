from __future__ import annotations

from py2cpp.semantic.exceptions import (
    cpp_exception_name,
    is_exception_ancestor,
    is_known_exception,
)


def test_known_exception_names() -> None:
    assert is_known_exception("ValueError")
    assert is_known_exception("Exception")
    assert not is_known_exception("NotAnException")


def test_direct_ancestor() -> None:
    assert is_exception_ancestor("ValueError", "Exception")
    assert is_exception_ancestor("IndexError", "LookupError")


def test_transitive_ancestor() -> None:
    assert is_exception_ancestor("ZeroDivisionError", "ArithmeticError")
    assert is_exception_ancestor("ZeroDivisionError", "Exception")
    assert is_exception_ancestor("IndexError", "Exception")


def test_self_is_its_own_ancestor() -> None:
    assert is_exception_ancestor("ValueError", "ValueError")


def test_unrelated_types_are_not_ancestors() -> None:
    assert not is_exception_ancestor("ValueError", "TypeError")
    assert not is_exception_ancestor("IndexError", "KeyError")
    assert not is_exception_ancestor("Exception", "ValueError")


def test_cpp_exception_name_maps_root() -> None:
    assert cpp_exception_name("Exception") == "PyException"
    assert cpp_exception_name("ValueError") == "ValueError"
