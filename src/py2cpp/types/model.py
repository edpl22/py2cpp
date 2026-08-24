"""The internal compiler type system.

Types are real objects, not strings: every stage (symbol table, IR,
backend) shares one source of truth for what a Python value's C++
representation should be. Only the types this milestone's subset actually
needs are defined here; FloatType, StringType, container types, and so on
are added when their milestones require them.
"""

from __future__ import annotations

from dataclasses import dataclass


class Type:
    """Base class for every py2cpp internal type."""


@dataclass(frozen=True)
class IntType(Type):
    def __str__(self) -> str:
        return "int"


@dataclass(frozen=True)
class BoolType(Type):
    def __str__(self) -> str:
        return "bool"


@dataclass(frozen=True)
class StringType(Type):
    def __str__(self) -> str:
        return "str"


@dataclass(frozen=True)
class ListType(Type):
    element_type: Type

    def __str__(self) -> str:
        return f"list[{self.element_type}]"


@dataclass(frozen=True)
class DictType(Type):
    key_type: Type
    value_type: Type

    def __str__(self) -> str:
        return f"dict[{self.key_type}, {self.value_type}]"


@dataclass(frozen=True)
class SetType(Type):
    element_type: Type

    def __str__(self) -> str:
        return f"set[{self.element_type}]"


@dataclass(frozen=True)
class TupleType(Type):
    element_types: tuple[Type, ...]

    def __str__(self) -> str:
        return f"tuple[{', '.join(str(t) for t in self.element_types)}]"
