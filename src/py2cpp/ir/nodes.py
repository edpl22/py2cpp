"""Typed intermediate representation for py2cpp.

IR nodes represent semantic intent rather than reproducing ast.AST shapes:
every expression node carries its resolved Type, so the backend never has
to re-derive anything from names or the symbol table -- it only formats.
Only the node kinds the currently-supported subset needs are defined
here; container/class/exception nodes and so on are added when their
milestones require them.
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


class CompareOp(Enum):
    EQ = auto()
    NE = auto()
    LT = auto()
    LE = auto()
    GT = auto()
    GE = auto()


class LogicalOp(Enum):
    AND = auto()
    OR = auto()


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
class IRCompare:
    op: CompareOp
    left: IRExpr
    right: IRExpr
    type: Type


@dataclass(frozen=True)
class IRLogicalExpr:
    op: LogicalOp
    left: IRExpr
    right: IRExpr
    type: Type


@dataclass(frozen=True)
class IRNot:
    operand: IRExpr
    type: Type


@dataclass(frozen=True)
class IRTruthy:
    """Converts an int to bool for use as a condition (nonzero = true),
    matching Python's general truthiness for the types this milestone
    supports.
    """

    operand: IRExpr
    type: Type


@dataclass(frozen=True)
class IRCall:
    callee: str
    args: tuple[IRExpr, ...]
    type: Type


IRExpr = IRLiteral | IRVarRef | IRBinaryExpr | IRCompare | IRLogicalExpr | IRNot | IRTruthy | IRCall


@dataclass(frozen=True)
class IRReturn:
    value: IRExpr
    location: SourceLocation


@dataclass(frozen=True)
class IRPrintStmt:
    args: tuple[IRExpr, ...]
    location: SourceLocation


@dataclass(frozen=True)
class IRExprStmt:
    expr: IRExpr
    location: SourceLocation


@dataclass(frozen=True)
class IRAssign:
    name: str
    value: IRExpr
    type: Type
    declare: bool
    location: SourceLocation


@dataclass(frozen=True)
class IRIf:
    condition: IRExpr
    then_body: tuple[IRStmt, ...]
    else_body: tuple[IRStmt, ...]
    location: SourceLocation


@dataclass(frozen=True)
class IRWhile:
    condition: IRExpr
    body: tuple[IRStmt, ...]
    location: SourceLocation


@dataclass(frozen=True)
class IRFor:
    var: str
    start: IRExpr
    stop: IRExpr
    step: int
    body: tuple[IRStmt, ...]
    location: SourceLocation


IRStmt = IRReturn | IRPrintStmt | IRExprStmt | IRAssign | IRIf | IRWhile | IRFor


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
