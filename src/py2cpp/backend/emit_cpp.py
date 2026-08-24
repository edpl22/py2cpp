"""IR -> C++17 backend.

This module is a pure, mechanical translator: every fact it needs (types,
resolved names, arities) is already attached to the IR by the time it
arrives here. It never re-derives semantics or re-consults the symbol
table.

Comparisons and 'and'/'or'/'not' map directly to native C++ operators
(no pyrt helper) because ir/lower.py already restricts their operands to
bool, where C++'s semantics are identical to Python's: no overflow is
possible, and short-circuit evaluation of already-boolean operands is
indistinguishable from Python returning "one of the operands".
"""

from __future__ import annotations

from py2cpp.backend.mangling import escape_identifier
from py2cpp.backend.types_cpp import cpp_type
from py2cpp.backend.writer import CodeWriter
from py2cpp.ir.nodes import (
    BinaryOp,
    CompareOp,
    IRAssign,
    IRBinaryExpr,
    IRCall,
    IRCompare,
    IRExpr,
    IRExprStmt,
    IRFor,
    IRFunction,
    IRIf,
    IRLiteral,
    IRLogicalExpr,
    IRModule,
    IRNot,
    IRParameter,
    IRPrintStmt,
    IRReturn,
    IRStmt,
    IRTruthy,
    IRVarRef,
    IRWhile,
    LogicalOp,
)

_BINARY_OP_HELPER = {
    BinaryOp.ADD: "pyrt::add",
    BinaryOp.SUB: "pyrt::sub",
    BinaryOp.MUL: "pyrt::mul",
}
_COMPARE_OP_SYMBOL = {
    CompareOp.EQ: "==",
    CompareOp.NE: "!=",
    CompareOp.LT: "<",
    CompareOp.LE: "<=",
    CompareOp.GT: ">",
    CompareOp.GE: ">=",
}
_LOGICAL_OP_SYMBOL = {
    LogicalOp.AND: "&&",
    LogicalOp.OR: "||",
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
    elif isinstance(stmt, IRExprStmt):
        writer.write_line(f"{_emit_expr(stmt.expr)};")
    elif isinstance(stmt, IRAssign):
        name = escape_identifier(stmt.name)
        value = _emit_expr(stmt.value)
        if stmt.declare:
            writer.write_line(f"{cpp_type(stmt.type)} {name} = {value};")
        else:
            writer.write_line(f"{name} = {value};")
    elif isinstance(stmt, IRIf):
        _emit_if(writer, stmt)
    elif isinstance(stmt, IRWhile):
        writer.write_line(f"while ({_emit_condition(stmt.condition)}) {{")
        writer.indent()
        for inner in stmt.body:
            _emit_stmt(writer, inner)
        writer.dedent()
        writer.write_line("}")
    elif isinstance(stmt, IRFor):
        _emit_for(writer, stmt)
    else:
        raise TypeError(f"unhandled IR statement: {stmt!r}")  # pragma: no cover


def _emit_if(writer: CodeWriter, stmt: IRIf) -> None:
    # Python's 'elif' lowers to a single-statement else_body containing
    # another IRIf; collapsing that back into a C++ "else if" chain here
    # (rather than nesting a brace block per elif) is what keeps the
    # output "reasonably human-written" instead of a staircase of braces.
    writer.write_line(f"if ({_emit_condition(stmt.condition)}) {{")
    writer.indent()
    for inner in stmt.then_body:
        _emit_stmt(writer, inner)
    writer.dedent()

    else_body = stmt.else_body
    while len(else_body) == 1 and isinstance(else_body[0], IRIf):
        elif_stmt = else_body[0]
        writer.write_line(f"}} else if ({_emit_condition(elif_stmt.condition)}) {{")
        writer.indent()
        for inner in elif_stmt.then_body:
            _emit_stmt(writer, inner)
        writer.dedent()
        else_body = elif_stmt.else_body

    if else_body:
        writer.write_line("} else {")
        writer.indent()
        for inner in else_body:
            _emit_stmt(writer, inner)
        writer.dedent()
    writer.write_line("}")


def _emit_for(writer: CodeWriter, stmt: IRFor) -> None:
    var = escape_identifier(stmt.var)
    start = _emit_expr(stmt.start)
    stop = _emit_expr(stmt.stop)
    comparison = "<" if stmt.step > 0 else ">"
    writer.write_line(
        f"for (std::int64_t {var} = {start}; {var} {comparison} {stop}; "
        f"{var} = pyrt::add({var}, {stmt.step})) {{"
    )
    writer.indent()
    for inner in stmt.body:
        _emit_stmt(writer, inner)
    writer.dedent()
    writer.write_line("}")


def _emit_condition(expr: IRExpr) -> str:
    """Like _emit_expr, but for direct use inside if(...)/while(...), which
    already supplies the delimiting parens -- avoids the doubled-up
    "if ((x < y))" that _emit_expr's own self-parenthesizing would
    otherwise produce for a Compare/Logical/Not/Truthy condition.
    """

    if isinstance(expr, (IRCompare, IRLogicalExpr, IRNot, IRTruthy)):
        emitted = _emit_expr(expr)
        return emitted[1:-1]
    return _emit_expr(expr)


def _emit_expr(expr: IRExpr) -> str:
    if isinstance(expr, IRLiteral):
        return str(expr.value)
    if isinstance(expr, IRVarRef):
        return escape_identifier(expr.name)
    if isinstance(expr, IRBinaryExpr):
        helper = _BINARY_OP_HELPER[expr.op]
        return f"{helper}({_emit_expr(expr.left)}, {_emit_expr(expr.right)})"
    if isinstance(expr, IRCompare):
        symbol = _COMPARE_OP_SYMBOL[expr.op]
        return f"({_emit_expr(expr.left)} {symbol} {_emit_expr(expr.right)})"
    if isinstance(expr, IRLogicalExpr):
        symbol = _LOGICAL_OP_SYMBOL[expr.op]
        return f"({_emit_expr(expr.left)} {symbol} {_emit_expr(expr.right)})"
    if isinstance(expr, IRNot):
        return f"(!{_emit_expr(expr.operand)})"
    if isinstance(expr, IRTruthy):
        return f"({_emit_expr(expr.operand)} != 0)"
    if isinstance(expr, IRCall):
        args = ", ".join(_emit_expr(arg) for arg in expr.args)
        return f"{escape_identifier(expr.callee)}({args})"
    raise TypeError(f"unhandled IR expression: {expr!r}")  # pragma: no cover
