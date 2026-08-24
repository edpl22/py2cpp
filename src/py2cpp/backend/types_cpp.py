"""Maps py2cpp internal Type instances to their C++ spelling."""

from __future__ import annotations

from py2cpp.backend.mangling import escape_identifier
from py2cpp.types.model import (
    BoolType,
    ClassType,
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
    if isinstance(t, ClassType):
        # Class instances are reference-typed (see HANDOFF.md Decision D's
        # accompanying object-aliasing decision): every variable, field, or
        # parameter of a class type holds a shared_ptr to the instance, so
        # 'a = b' aliases like Python's object identity rather than copying.
        return f"std::shared_ptr<{escape_identifier(t.name)}>"
    raise TypeError(f"no C++ representation registered for type {t!r}")
