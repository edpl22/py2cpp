"""Maps py2cpp internal Type instances to their C++ spelling."""

from __future__ import annotations

from py2cpp.types.model import (
    BoolType,
    DictType,
    IntType,
    ListType,
    SetType,
    StringType,
    TupleType,
    Type,
)


def cpp_type(t: Type) -> str:
    if isinstance(t, IntType):
        return "std::int64_t"
    if isinstance(t, BoolType):
        return "bool"
    if isinstance(t, StringType):
        return "pyrt::Str"
    if isinstance(t, ListType):
        return f"pyrt::List<{cpp_type(t.element_type)}>"
    if isinstance(t, DictType):
        return f"pyrt::Dict<{cpp_type(t.key_type)}, {cpp_type(t.value_type)}>"
    if isinstance(t, SetType):
        return f"pyrt::Set<{cpp_type(t.element_type)}>"
    if isinstance(t, TupleType):
        elements = ", ".join(cpp_type(e) for e in t.element_types)
        return f"std::tuple<{elements}>"
    raise TypeError(f"no C++ representation registered for type {t!r}")
