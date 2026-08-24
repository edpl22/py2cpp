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
    IRStringLiteral,
    IRToStr,
    IRVarRef,
)
from py2cpp.types.model import IntType, StringType

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


def test_emits_string_literal_and_concatenation() -> None:
    function = IRFunction(
        name="greet",
        parameters=(IRParameter(name="name", type=StringType()),),
        return_type=StringType(),
        body=(
            IRReturn(
                value=IRBinaryExpr(
                    op=BinaryOp.ADD,
                    left=IRStringLiteral(value="hello, ", type=StringType()),
                    right=IRVarRef(name="name", type=StringType()),
                    type=StringType(),
                ),
                location=_LOCATION,
            ),
        ),
        location=_LOCATION,
    )
    module = IRModule(name="greet", functions=(function,), main_body=())

    output = emit_module(module)

    assert "pyrt::Str greet(pyrt::Str name) {" in output
    assert 'return (pyrt::Str("hello, ") + name);' in output


def test_emits_to_str_conversion() -> None:
    function = IRFunction(
        name="describe",
        parameters=(IRParameter(name="n", type=IntType()),),
        return_type=StringType(),
        body=(
            IRReturn(
                value=IRToStr(operand=IRVarRef(name="n", type=IntType()), type=StringType()),
                location=_LOCATION,
            ),
        ),
        location=_LOCATION,
    )
    module = IRModule(name="describe", functions=(function,), main_body=())

    output = emit_module(module)

    assert "return pyrt::str(n);" in output
