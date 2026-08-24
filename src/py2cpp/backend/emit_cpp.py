"""IR -> C++17 backend.

This module is a pure, mechanical translator: every fact it needs (types,
resolved names, arities) is already attached to the IR by the time it
arrives here. It never re-derives semantics or re-consults the symbol
table.
"""

from __future__ import annotations

from py2cpp.backend.mangling import escape_identifier
from py2cpp.backend.types_cpp import cpp_type
from py2cpp.backend.writer import CodeWriter
from py2cpp.ir.nodes import (
    BinaryOp,
    IRBinaryExpr,
    IRCall,
    IRExpr,
    IRFunction,
    IRLiteral,
    IRModule,
    IRParameter,
    IRPrintStmt,
    IRReturn,
    IRStmt,
    IRVarRef,
)

_BINARY_OP_HELPER = {
    BinaryOp.ADD: "pyrt::add",
    BinaryOp.SUB: "pyrt::sub",
    BinaryOp.MUL: "pyrt::mul",
}


def emit_module(module: IRModule) -> str:
    writer = CodeWriter()
    writer.write_line("#include <cstdint>")
    writer.write_line('#include "pyrt/pyrt.hpp"')
    writer.write_line()

    for function in module.functions:
        _emit_function(writer, function)
        writer.write_line()

    writer.write_line("int main() {")
    writer.indent()
    for stmt in module.main_body:
        _emit_stmt(writer, stmt)
    writer.write_line("return 0;")
    writer.dedent()
    writer.write_line("}")
    return writer.render()


def _emit_function(writer: CodeWriter, function: IRFunction) -> None:
    params = ", ".join(_emit_parameter(p) for p in function.parameters)
    name = escape_identifier(function.name)
    writer.write_line(f"{cpp_type(function.return_type)} {name}({params}) {{")
    writer.indent()
    for stmt in function.body:
        _emit_stmt(writer, stmt)
    writer.dedent()
    writer.write_line("}")


def _emit_parameter(parameter: IRParameter) -> str:
    return f"{cpp_type(parameter.type)} {escape_identifier(parameter.name)}"


def _emit_stmt(writer: CodeWriter, stmt: IRStmt) -> None:
    if isinstance(stmt, IRReturn):
        writer.write_line(f"return {_emit_expr(stmt.value)};")
    elif isinstance(stmt, IRPrintStmt):
        args = ", ".join(_emit_expr(arg) for arg in stmt.args)
        writer.write_line(f"pyrt::print({args});")
    else:
        raise TypeError(f"unhandled IR statement: {stmt!r}")  # pragma: no cover


def _emit_expr(expr: IRExpr) -> str:
    if isinstance(expr, IRLiteral):
        return str(expr.value)
    if isinstance(expr, IRVarRef):
        return escape_identifier(expr.name)
    if isinstance(expr, IRBinaryExpr):
        helper = _BINARY_OP_HELPER[expr.op]
        return f"{helper}({_emit_expr(expr.left)}, {_emit_expr(expr.right)})"
    if isinstance(expr, IRCall):
        args = ", ".join(_emit_expr(arg) for arg in expr.args)
        return f"{escape_identifier(expr.callee)}({args})"
    raise TypeError(f"unhandled IR expression: {expr!r}")  # pragma: no cover
