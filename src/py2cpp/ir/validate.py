"""Final invariant checks over the IR before it reaches the backend.

Anything caught here indicates a py2cpp bug -- an earlier stage produced
IR that violates its own contract -- not a problem with the user's
program. User-facing problems are always diagnosed before IR construction
is attempted (lower_module only returns a module once zero diagnostics
were reported).
"""

from __future__ import annotations

from collections.abc import Sequence

from py2cpp.ir.nodes import (
    IRAssign,
    IRAttributeAssign,
    IRClassDef,
    IRExprStmt,
    IRFor,
    IRForEach,
    IRFunction,
    IRIf,
    IRMethod,
    IRModule,
    IRPrintStmt,
    IRReturn,
    IRStmt,
    IRWhile,
)
from py2cpp.types.join import is_assignable
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


class InternalCompilerError(Exception):
    """Raised when the IR violates an invariant the earlier stages are
    supposed to guarantee. This always indicates a bug in py2cpp.
    """


def validate_module(module: IRModule) -> None:
    seen_names: set[str] = set()
    for class_def in module.classes:
        if class_def.name in seen_names:
            raise InternalCompilerError(f"duplicate class '{class_def.name}' reached the IR")
        seen_names.add(class_def.name)
        _validate_class(class_def)

    for function in module.functions:
        if function.name in seen_names:
            raise InternalCompilerError(f"duplicate function '{function.name}' reached the IR")
        seen_names.add(function.name)
        _validate_function(function)

    _validate_statements(module.main_body)


def _assignable_or_class(value_type: Type, target_type: Type) -> bool:
    """Like is_assignable, but trusts ir/lower.py's own class-hierarchy
    subtyping check for two class-typed values rather than re-deriving it
    here -- this final-invariant layer has no SymbolTable (class shape
    knowledge) available, and doesn't need one for anything else.
    """

    if isinstance(target_type, ClassType):
        return isinstance(value_type, ClassType)
    return is_assignable(value_type, target_type)


def _validate_function(function: IRFunction) -> None:
    if not function.body or not isinstance(function.body[-1], IRReturn):
        raise InternalCompilerError(
            f"function '{function.name}' body must end in a 'return' statement"
        )
    _validate_statements(function.body[:-1])

    return_stmt = function.body[-1]
    if not _assignable_or_class(return_stmt.value.type, function.return_type):
        raise InternalCompilerError(
            f"function '{function.name}' declares return type {function.return_type} "
            f"but its return value has type {return_stmt.value.type}"
        )


def _validate_class(class_def: IRClassDef) -> None:
    _validate_statements(class_def.constructor.body)
    for method in class_def.methods:
        _validate_method(class_def, method)


def _validate_method(class_def: IRClassDef, method: IRMethod) -> None:
    if not method.body or not isinstance(method.body[-1], IRReturn):
        raise InternalCompilerError(
            f"method '{class_def.name}.{method.name}' body must end in a 'return' statement"
        )
    _validate_statements(method.body[:-1])

    return_stmt = method.body[-1]
    if not _assignable_or_class(return_stmt.value.type, method.return_type):
        raise InternalCompilerError(
            f"method '{class_def.name}.{method.name}' declares return type {method.return_type} "
            f"but its return value has type {return_stmt.value.type}"
        )


def _validate_statements(stmts: Sequence[IRStmt]) -> None:
    for stmt in stmts:
        _validate_stmt(stmt)


def _validate_stmt(stmt: IRStmt) -> None:
    if isinstance(stmt, IRReturn):
        raise InternalCompilerError("'return' reached the IR outside a function's final position")
    if isinstance(stmt, IRPrintStmt):
        for arg in stmt.args:
            if not isinstance(
                arg.type, (IntType, BoolType, StringType, ListType, DictType, SetType, TupleType)
            ):
                raise InternalCompilerError(f"'print' argument has unsupported type {arg.type}")
    elif isinstance(stmt, IRExprStmt):
        pass
    elif isinstance(stmt, IRAssign):
        if not _assignable_or_class(stmt.value.type, stmt.type):
            raise InternalCompilerError(
                f"'{stmt.name}' is declared {stmt.type} but assigned a value of type "
                f"{stmt.value.type}"
            )
    elif isinstance(stmt, IRAttributeAssign):
        if not isinstance(stmt.obj.type, ClassType):
            raise InternalCompilerError(
                f"attribute assignment target must be class-typed, got {stmt.obj.type}"
            )
        if not _assignable_or_class(stmt.value.type, stmt.type):
            raise InternalCompilerError(
                f"attribute '{stmt.attr}' is declared {stmt.type} but assigned a value of type "
                f"{stmt.value.type}"
            )
    elif isinstance(stmt, IRIf):
        if not isinstance(stmt.condition.type, BoolType):
            raise InternalCompilerError("'if' condition reaching the IR must be 'bool'")
        _validate_statements(stmt.then_body)
        _validate_statements(stmt.else_body)
    elif isinstance(stmt, IRWhile):
        if not isinstance(stmt.condition.type, BoolType):
            raise InternalCompilerError("'while' condition reaching the IR must be 'bool'")
        _validate_statements(stmt.body)
    elif isinstance(stmt, IRFor):
        if stmt.step == 0:
            raise InternalCompilerError("'for' step reaching the IR must not be zero")
        _validate_statements(stmt.body)
    elif isinstance(stmt, IRForEach):
        _validate_statements(stmt.body)
    else:
        raise InternalCompilerError(f"unexpected IR statement: {stmt!r}")  # pragma: no cover
