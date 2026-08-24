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


@dataclass
class SymbolTable:
    functions: dict[str, FunctionSymbol] = field(default_factory=dict)
