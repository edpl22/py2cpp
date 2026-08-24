"""Maps py2cpp internal Type instances to their C++ spelling."""

from __future__ import annotations

from py2cpp.types.model import BoolType, IntType, Type


def cpp_type(t: Type) -> str:
    if isinstance(t, IntType):
        return "std::int64_t"
    if isinstance(t, BoolType):
        return "bool"
    raise TypeError(f"no C++ representation registered for type {t!r}")
