"""The symbol table: functions, parameters, and their declared types."""

from __future__ import annotations

from dataclasses import dataclass, field

from py2cpp.diagnostics import SourceLocation
from py2cpp.types.model import Type


@dataclass(frozen=True)
class ParameterSymbol:
    name: str
    type: Type
    location: SourceLocation


@dataclass(frozen=True)
class FunctionSymbol:
    name: str
    parameters: tuple[ParameterSymbol, ...]
    return_type: Type
    location: SourceLocation

    @property
    def arity(self) -> int:
        return len(self.parameters)


@dataclass(frozen=True)
class AttributeSymbol:
    name: str
    type: Type
    location: SourceLocation


@dataclass(frozen=True)
class MethodSymbol:
    """A class method's signature. 'parameters' excludes 'self' -- self's
    type is always the enclosing class, so it never needs an annotation
    and is threaded in separately wherever a method is looked up.
    """

    name: str
    parameters: tuple[ParameterSymbol, ...]
    return_type: Type
    location: SourceLocation

    @property
    def arity(self) -> int:
        return len(self.parameters)


@dataclass(frozen=True)
class ClassSymbol:
    """'attributes' and 'methods' hold only members declared directly on
    this class (not inherited ones) -- lookups that need the full,
    base-aware member set walk the base chain via SymbolTable.classes,
    see ir/lower.py's attribute/method resolution helpers.
    """

    name: str
    base: str | None
    init_parameters: tuple[ParameterSymbol, ...]
    attributes: dict[str, AttributeSymbol]
    methods: dict[str, MethodSymbol]
    location: SourceLocation


@dataclass
class SymbolTable:
    functions: dict[str, FunctionSymbol] = field(default_factory=dict)
    classes: dict[str, ClassSymbol] = field(default_factory=dict)
