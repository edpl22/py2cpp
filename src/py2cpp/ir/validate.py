"""Final invariant checks over the IR before it reaches the backend.

Anything caught here indicates a py2cpp bug -- an earlier stage produced
IR that violates its own contract -- not a problem with the user's
program. User-facing problems are always diagnosed before IR construction
is attempted (lower_module only returns a module once zero diagnostics
were reported).
"""

from __future__ import annotations

from py2cpp.ir.nodes import IRFunction, IRModule, IRPrintStmt, IRReturn
from py2cpp.types.model import IntType


class InternalCompilerError(Exception):
    """Raised when the IR violates an invariant the earlier stages are
    supposed to guarantee. This always indicates a bug in py2cpp.
    """


def validate_module(module: IRModule) -> None:
    seen_names: set[str] = set()
    for function in module.functions:
        if function.name in seen_names:
            raise InternalCompilerError(f"duplicate function '{function.name}' reached the IR")
        seen_names.add(function.name)
        _validate_function(function)

    for stmt in module.main_body:
        if not isinstance(stmt, IRPrintStmt):
            raise InternalCompilerError(f"unexpected top-level IR statement: {stmt!r}")
        for arg in stmt.args:
            if not isinstance(arg.type, IntType):
                raise InternalCompilerError(f"'print' argument has non-int type {arg.type}")


def _validate_function(function: IRFunction) -> None:
    if len(function.body) != 1 or not isinstance(function.body[0], IRReturn):
        raise InternalCompilerError(
            f"function '{function.name}' body must be exactly one return statement"
        )
    value = function.body[0].value
    if value.type != function.return_type:
        raise InternalCompilerError(
            f"function '{function.name}' declares return type {function.return_type} "
            f"but its return value has type {value.type}"
        )
