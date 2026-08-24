from __future__ import annotations

from pathlib import Path

import pytest

from py2cpp.diagnostics import SourceLocation
from py2cpp.ir.nodes import IRFunction, IRModule, IRReturn, IRVarRef
from py2cpp.ir.validate import InternalCompilerError, validate_module
from py2cpp.types.model import IntType

_LOCATION = SourceLocation(filename=Path("test.py"), line=1, column=1)


def test_valid_module_passes() -> None:
    function = IRFunction(
        name="identity",
        parameters=(),
        return_type=IntType(),
        body=(IRReturn(value=IRVarRef(name="a", type=IntType()), location=_LOCATION),),
        location=_LOCATION,
    )
    module = IRModule(name="m", functions=(function,), main_body=())
    validate_module(module)  # must not raise


def test_return_type_mismatch_raises_internal_error() -> None:
    from py2cpp.types.model import Type

    class _BogusType(Type):
        def __str__(self) -> str:
            return "bogus"

    function = IRFunction(
        name="identity",
        parameters=(),
        return_type=IntType(),
        body=(IRReturn(value=IRVarRef(name="a", type=_BogusType()), location=_LOCATION),),
        location=_LOCATION,
    )
    module = IRModule(name="m", functions=(function,), main_body=())

    with pytest.raises(InternalCompilerError):
        validate_module(module)


def test_duplicate_function_name_raises_internal_error() -> None:
    function = IRFunction(
        name="identity",
        parameters=(),
        return_type=IntType(),
        body=(IRReturn(value=IRVarRef(name="a", type=IntType()), location=_LOCATION),),
        location=_LOCATION,
    )
    module = IRModule(name="m", functions=(function, function), main_body=())

    with pytest.raises(InternalCompilerError):
        validate_module(module)
