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
