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
from py2cpp.backend.string_literals import cpp_string_literal
from py2cpp.backend.types_cpp import cpp_type
from py2cpp.backend.writer import CodeWriter
from py2cpp.ir.nodes import (
    BinaryOp,
    CompareOp,
    IRAssign,
    IRAttributeAccess,
    IRAttributeAssign,
    IRBinaryExpr,
    IRCall,
    IRClassDef,
    IRCompare,
    IRConstruct,
    IRDictLiteral,
    IRExceptHandler,
    IRExpr,
    IRExprStmt,
    IRFor,
    IRForEach,
    IRFunction,
    IRIf,
    IRIndex,
    IRListCompForEach,
    IRListCompRange,
    IRListLiteral,
    IRLiteral,
    IRLogicalExpr,
    IRMethod,
    IRMethodCall,
    IRModule,
    IRNot,
    IRParameter,
    IRPrintStmt,
    IRRaise,
    IRReturn,
    IRSetLiteral,
    IRStmt,
    IRStringLiteral,
    IRToStr,
    IRTruthy,
    IRTry,
    IRTupleIndex,
    IRTupleLiteral,
    IRVarRef,
    IRWhile,
    LogicalOp,
)
from py2cpp.semantic.exceptions import cpp_exception_name
from py2cpp.types.model import DictType, ListType, SetType, StringType

_SELF = "self"

_BINARY_OP_HELPER = {
    BinaryOp.ADD: "pyrt::add",
    BinaryOp.SUB: "pyrt::sub",
    BinaryOp.MUL: "pyrt::mul",
    BinaryOp.FLOORDIV: "pyrt::floordiv",
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
    writer.write_line("#include <memory>")
    writer.write_line('#include "pyrt/pyrt.hpp"')
    writer.write_line()

    if module.classes:
        # Forward-declare every class before any full definition: an
        # attribute/parameter/return type may reference another class
        # defined later in the file (or itself, e.g. a linked-structure
        # 'next' field) -- std::shared_ptr<T> only needs T to be a known
        # type name, not a complete one, at the point of declaration, so
        # this alone is enough to make forward and self references work
        # regardless of the classes' definition order.
        for class_def in module.classes:
            writer.write_line(f"struct {escape_identifier(class_def.name)};")
        writer.write_line()

        for class_def in module.classes:
            _emit_class(writer, class_def)
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


def _emit_class(writer: CodeWriter, class_def: IRClassDef) -> None:
    name = escape_identifier(class_def.name)
    header = f"struct {name}"
    if class_def.base is not None:
        header += f" : {escape_identifier(class_def.base)}"
    writer.write_line(header + " {")
    writer.indent()

    for attr in class_def.attributes:
        # A default member initializer ('{}') keeps every field
        # value-initialized from the moment the object exists, so there's
        # no window where a field holds an indeterminate value -- even
        # though the constructor body (below) unconditionally overwrites
        # every declared attribute before the object is ever handed out.
        writer.write_line(f"{cpp_type(attr.type)} {escape_identifier(attr.name)}{{}};")
    if class_def.attributes:
        writer.write_line()

    _emit_constructor(writer, class_def)
    writer.write_line()

    for method in class_def.methods:
        _emit_method(writer, method)
        writer.write_line()

    if class_def.needs_virtual_destructor:
        writer.write_line(f"virtual ~{name}() = default;")

    writer.dedent()
    writer.write_line("};")


def _emit_constructor(writer: CodeWriter, class_def: IRClassDef) -> None:
    name = escape_identifier(class_def.name)
    params = ", ".join(_emit_parameter(p) for p in class_def.constructor.parameters)
    header = f"{name}({params})"
    if class_def.constructor.base_args is not None:
        base_args = ", ".join(_emit_expr(a) for a in class_def.constructor.base_args)
        assert class_def.base is not None
        header += f" : {escape_identifier(class_def.base)}({base_args})"
    writer.write_line(header + " {")
    writer.indent()
    for stmt in class_def.constructor.body:
        _emit_stmt(writer, stmt)
    writer.dedent()
    writer.write_line("}")


def _emit_method(writer: CodeWriter, method: IRMethod) -> None:
    params = ", ".join(_emit_parameter(p) for p in method.parameters)
    name = escape_identifier(method.name)
    prefix = "virtual " if method.is_virtual and not method.is_override else ""
    suffix = " override" if method.is_override else ""
    writer.write_line(f"{prefix}{cpp_type(method.return_type)} {name}({params}){suffix} {{")
    writer.indent()
    for stmt in method.body:
        _emit_stmt(writer, stmt)
    writer.dedent()
    writer.write_line("}")


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
    elif isinstance(stmt, IRAttributeAssign):
        attr = escape_identifier(stmt.attr)
        writer.write_line(f"{_emit_expr(stmt.obj)}->{attr} = {_emit_expr(stmt.value)};")
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
    elif isinstance(stmt, IRForEach):
        _emit_for_each(writer, stmt)
    elif isinstance(stmt, IRTry):
        _emit_try(writer, stmt)
    elif isinstance(stmt, IRRaise):
        _emit_raise(writer, stmt)
    else:
        raise TypeError(f"unhandled IR statement: {stmt!r}")  # pragma: no cover


def _emit_try(writer: CodeWriter, stmt: IRTry) -> None:
    # Each handler's own leading '} catch (...) {' merges with whatever
    # precedes it (the try body's close, or the previous handler's close)
    # -- mirrors _emit_if's elif-chain merging below. Only one standalone
    # closing brace is ever written, after the very last handler.
    writer.write_line("try {")
    writer.indent()
    for inner in stmt.body:
        _emit_stmt(writer, inner)
    writer.dedent()
    for handler in stmt.handlers:
        _emit_except_header(writer, handler)
        writer.indent()
        for inner in handler.body:
            _emit_stmt(writer, inner)
        writer.dedent()
    writer.write_line("}")


def _emit_except_header(writer: CodeWriter, handler: IRExceptHandler) -> None:
    if handler.exception_type is None:
        writer.write_line("} catch (...) {")
        return
    cpp_name = f"pyrt::{cpp_exception_name(handler.exception_type)}"
    if handler.bound_name is not None:
        bound = escape_identifier(handler.bound_name)
        writer.write_line(f"}} catch (const {cpp_name}& {bound}) {{")
    else:
        writer.write_line(f"}} catch (const {cpp_name}&) {{")


def _emit_raise(writer: CodeWriter, stmt: IRRaise) -> None:
    if stmt.exception_type is None:
        writer.write_line("throw;")
        return
    cpp_name = f"pyrt::{cpp_exception_name(stmt.exception_type)}"
    message = _emit_expr(stmt.message) if stmt.message is not None else "pyrt::Str()"
    writer.write_line(f"throw {cpp_name}({message});")


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


def _emit_for_each(writer: CodeWriter, stmt: IRForEach) -> None:
    var = escape_identifier(stmt.var)
    iterable = _emit_expr(stmt.iterable)
    if isinstance(stmt.iterable.type, DictType):
        # Python 'for k in d' iterates keys only; pyrt::Dict's own
        # begin()/end() yields key/value pairs (see dict.hpp), so bind the
        # loop variable to '.first' of each one.
        writer.write_line(f"for (const auto& __pyrt_pair : {iterable}) {{")
        writer.indent()
        writer.write_line(f"{cpp_type(stmt.var_type)} {var} = __pyrt_pair.first;")
        for inner in stmt.body:
            _emit_stmt(writer, inner)
        writer.dedent()
        writer.write_line("}")
        return

    writer.write_line(f"for (const auto& {var} : {iterable}) {{")
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
    if isinstance(expr, IRStringLiteral):
        return f"pyrt::Str({cpp_string_literal(expr.value)})"
    if isinstance(expr, IRToStr):
        return f"pyrt::str({_emit_expr(expr.operand)})"
    if isinstance(expr, IRVarRef):
        if expr.name == _SELF:
            # Methods are real C++ member functions (needed for virtual
            # dispatch), so there's no 'self' parameter at all in the
            # emitted signature -- 'self' is always 'this' instead, which
            # IRAttributeAccess/IRAttributeAssign/IRMethodCall's uniform
            # 'obj->member' emission handles with no further special-casing.
            return "this"
        return escape_identifier(expr.name)
    if isinstance(expr, IRBinaryExpr):
        if isinstance(expr.type, StringType):
            # String '+' is native pyrt::Str concatenation, not the
            # overflow-checked int helper -- overflow doesn't apply here.
            return f"({_emit_expr(expr.left)} + {_emit_expr(expr.right)})"
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
    if isinstance(expr, IRListLiteral):
        assert isinstance(expr.type, ListType)
        elem_type = cpp_type(expr.type.element_type)
        elements = ", ".join(_emit_expr(e) for e in expr.elements)
        return f"pyrt::List<{elem_type}>(std::deque<{elem_type}>{{{elements}}})"
    if isinstance(expr, IRSetLiteral):
        assert isinstance(expr.type, SetType)
        elem_type = cpp_type(expr.type.element_type)
        elements = ", ".join(_emit_expr(e) for e in expr.elements)
        return f"pyrt::Set<{elem_type}>(std::deque<{elem_type}>{{{elements}}})"
    if isinstance(expr, IRDictLiteral):
        return _emit_dict_literal(expr)
    if isinstance(expr, IRTupleLiteral):
        tuple_type = cpp_type(expr.type)
        elements = ", ".join(_emit_expr(e) for e in expr.elements)
        return f"{tuple_type}({elements})"
    if isinstance(expr, IRIndex):
        return f"{_emit_expr(expr.container)}.at({_emit_expr(expr.index)})"
    if isinstance(expr, IRTupleIndex):
        return f"std::get<{expr.index}>({_emit_expr(expr.tuple_expr)})"
    if isinstance(expr, IRListCompRange):
        return _emit_list_comp_range(expr)
    if isinstance(expr, IRListCompForEach):
        return _emit_list_comp_for_each(expr)
    if isinstance(expr, IRAttributeAccess):
        attr = escape_identifier(expr.attr)
        return f"{_emit_expr(expr.obj)}->{attr}"
    if isinstance(expr, IRMethodCall):
        method = escape_identifier(expr.method)
        args = ", ".join(_emit_expr(arg) for arg in expr.args)
        return f"{_emit_expr(expr.obj)}->{method}({args})"
    if isinstance(expr, IRConstruct):
        class_name = escape_identifier(expr.class_name)
        args = ", ".join(_emit_expr(arg) for arg in expr.args)
        return f"std::make_shared<{class_name}>({args})"
    raise TypeError(f"unhandled IR expression: {expr!r}")  # pragma: no cover


def _emit_dict_literal(expr: IRDictLiteral) -> str:
    dict_type = expr.type
    assert isinstance(dict_type, DictType)
    key_type = cpp_type(dict_type.key_type)
    value_type = cpp_type(dict_type.value_type)
    pairs = ", ".join(
        f"{{{_emit_expr(k)}, {_emit_expr(v)}}}" for k, v in zip(expr.keys, expr.values, strict=True)
    )
    return (
        f"pyrt::Dict<{key_type}, {value_type}>("
        f"std::vector<std::pair<{key_type}, {value_type}>>{{{pairs}}})"
    )


def _emit_list_comp_range(expr: IRListCompRange) -> str:
    var = escape_identifier(expr.var)
    elem_type = cpp_type(expr.element.type)
    start = _emit_expr(expr.start)
    stop = _emit_expr(expr.stop)
    comparison = "<" if expr.step > 0 else ">"
    lines = [
        f"std::deque<{elem_type}> __pyrt_result;",
        f"for (std::int64_t {var} = {start}; {var} {comparison} {stop}; "
        f"{var} = pyrt::add({var}, {expr.step})) {{",
    ]
    if expr.condition is not None:
        lines.append(f"    if (!({_emit_condition(expr.condition)})) continue;")
    lines.append(f"    __pyrt_result.push_back({_emit_expr(expr.element)});")
    lines.append("}")
    lines.append("return __pyrt_result;")
    body = "\n    ".join(lines)
    return f"pyrt::List<{elem_type}>([&]() {{\n    {body}\n}}())"


def _emit_list_comp_for_each(expr: IRListCompForEach) -> str:
    var = escape_identifier(expr.var)
    elem_type = cpp_type(expr.element.type)
    iterable = _emit_expr(expr.iterable)
    lines = [f"std::deque<{elem_type}> __pyrt_result;"]
    if isinstance(expr.iterable.type, DictType):
        lines.append(f"for (const auto& __pyrt_pair : {iterable}) {{")
        lines.append(f"    {cpp_type(expr.var_type)} {var} = __pyrt_pair.first;")
    else:
        lines.append(f"for (const auto& {var} : {iterable}) {{")
    if expr.condition is not None:
        lines.append(f"    if (!({_emit_condition(expr.condition)})) continue;")
    lines.append(f"    __pyrt_result.push_back({_emit_expr(expr.element)});")
    lines.append("}")
    lines.append("return __pyrt_result;")
    body = "\n    ".join(lines)
    return f"pyrt::List<{elem_type}>([&]() {{\n    {body}\n}}())"
