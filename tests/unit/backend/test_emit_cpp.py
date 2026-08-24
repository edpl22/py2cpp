"""Backend unit tests: hand-built IR in, exact C++ text out.

These never touch the parser or lowering pass -- see tests/unit/ir for
those. This is purely "does the emitter format this IR shape correctly".
"""

from __future__ import annotations

from pathlib import Path

from py2cpp.backend.emit_cpp import emit_module
from py2cpp.diagnostics import SourceLocation
from py2cpp.ir.nodes import (
    BinaryOp,
    IRBinaryExpr,
    IRFunction,
    IRModule,
    IRParameter,
    IRPrintStmt,
    IRReturn,
    IRVarRef,
)
from py2cpp.types.model import IntType

_LOCATION = SourceLocation(filename=Path("test.py"), line=1, column=1)


def test_emits_add_function_and_main() -> None:
    add_function = IRFunction(
        name="add",
        parameters=(IRParameter(name="a", type=IntType()), IRParameter(name="b", type=IntType())),
        return_type=IntType(),
        body=(
            IRReturn(
                value=IRBinaryExpr(
                    op=BinaryOp.ADD,
                    left=IRVarRef(name="a", type=IntType()),
                    right=IRVarRef(name="b", type=IntType()),
                    type=IntType(),
                ),
                location=_LOCATION,
            ),
        ),
        location=_LOCATION,
    )
    module = IRModule(
        name="add",
        functions=(add_function,),
        main_body=(
            IRPrintStmt(
                args=(
                    IRBinaryExpr(
                        op=BinaryOp.ADD,
                        left=IRVarRef(name="a", type=IntType()),
                        right=IRVarRef(name="b", type=IntType()),
                        type=IntType(),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert output == (
        "#include <cstdint>\n"
        '#include "pyrt/pyrt.hpp"\n'
        "\n"
        "std::int64_t add(std::int64_t a, std::int64_t b) {\n"
        "    return pyrt::add(a, b);\n"
        "}\n"
        "\n"
        "int main() {\n"
        "    pyrt::print(pyrt::add(a, b));\n"
        "    return 0;\n"
        "}\n"
    )


def test_keyword_parameter_name_is_escaped() -> None:
    function = IRFunction(
        name="identity",
        parameters=(IRParameter(name="class", type=IntType()),),
        return_type=IntType(),
        body=(IRReturn(value=IRVarRef(name="class", type=IntType()), location=_LOCATION),),
        location=_LOCATION,
    )
    module = IRModule(name="identity", functions=(function,), main_body=())

    output = emit_module(module)

    assert "std::int64_t identity(std::int64_t class_)" in output
    assert "return class_;" in output
