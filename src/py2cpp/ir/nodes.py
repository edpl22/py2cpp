"""Typed intermediate representation for py2cpp.

IR nodes represent semantic intent rather than reproducing ast.AST shapes:
every expression node carries its resolved Type, so the backend never has
to re-derive anything from names or the symbol table -- it only formats.
Only the node kinds this milestone's subset needs are defined here; IRIf,
IRWhile, IRAssign, container/class/exception nodes, and so on are added
when their milestones require them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from py2cpp.diagnostics import SourceLocation
from py2cpp.types.model import Type


class BinaryOp(Enum):
    ADD = auto()
    SUB = auto()
    MUL = auto()


@dataclass(frozen=True)
class IRLiteral:
    value: int
    type: Type


@dataclass(frozen=True)
class IRVarRef:
    name: str
    type: Type


@dataclass(frozen=True)
class IRBinaryExpr:
    op: BinaryOp
    left: IRExpr
    right: IRExpr
    type: Type


@dataclass(frozen=True)
class IRCall:
    callee: str
    args: tuple[IRExpr, ...]
    type: Type


IRExpr = IRLiteral | IRVarRef | IRBinaryExpr | IRCall


@dataclass(frozen=True)
class IRReturn:
    value: IRExpr
    location: SourceLocation


@dataclass(frozen=True)
class IRPrintStmt:
    args: tuple[IRExpr, ...]
    location: SourceLocation


IRStmt = IRReturn | IRPrintStmt


@dataclass(frozen=True)
class IRParameter:
    name: str
    type: Type


@dataclass(frozen=True)
class IRFunction:
    name: str
    parameters: tuple[IRParameter, ...]
    return_type: Type
    body: tuple[IRStmt, ...]
    location: SourceLocation


@dataclass(frozen=True)
class IRModule:
    name: str
    functions: tuple[IRFunction, ...]
    main_body: tuple[IRStmt, ...]
