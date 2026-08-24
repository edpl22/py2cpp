"""Lowers a validated Python AST into typed py2cpp IR.

This pass performs name resolution and type checking for expressions in
the same walk that builds IR nodes: for the tiny v1 grammar (annotated int
parameters, +/-/*, calls, return, print) splitting those into separate
tree-walks would just be three near-identical traversals of the same
handful of node kinds. A dedicated flow-sensitive types/infer.py stage is
introduced once M2 adds locals, branches, and real type joins -- at that
point the extra state a flow-sensitive pass needs justifies its own
module.

lower_module returns None once any diagnostic has been reported; callers
must not use a None result. It never raises for a user-error condition --
only ir.validate.InternalCompilerError, surfaced by the caller after
lowering, indicates a py2cpp bug.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.loader import SourceFile
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
from py2cpp.semantic.symbols import FunctionSymbol, SymbolTable
from py2cpp.types.model import IntType, Type

_BINOP_MAP: dict[type[ast.operator], BinaryOp] = {
    ast.Add: BinaryOp.ADD,
    ast.Sub: BinaryOp.SUB,
    ast.Mult: BinaryOp.MUL,
}

_PRINT_BUILTIN = "print"
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def lower_module(
    tree: ast.Module,
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
) -> IRModule | None:
    functions: list[IRFunction] = []
    main_body: list[IRStmt] = []

    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef):
            symbol = symtab.functions.get(stmt.name)
            if symbol is None or symbol.location != _location(source, stmt):
                # Either symbol collection already reported a diagnostic for
                # this definition, or it lost a duplicate-name race to an
                # earlier one; either way that's already been diagnosed.
                continue
            function = _lower_function(stmt, symbol, symtab, source, diagnostics)
            if function is not None:
                functions.append(function)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            ir_stmt = _lower_top_level_call(stmt.value, symtab, source, diagnostics)
            if ir_stmt is not None:
                main_body.append(ir_stmt)
        else:
            raise AssertionError(
                f"unexpected top-level statement after subset validation: {stmt!r}"
            )  # pragma: no cover

    if diagnostics.has_errors:
        return None
    return IRModule(name=source.path.stem, functions=tuple(functions), main_body=tuple(main_body))


def _location(source: SourceFile, node: ast.AST) -> SourceLocation:
    return SourceLocation(
        filename=source.path,
        line=getattr(node, "lineno", 1),
        column=getattr(node, "col_offset", 0) + 1,
    )


def _lower_function(
    node: ast.FunctionDef,
    symbol: FunctionSymbol,
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
) -> IRFunction | None:
    scope: dict[str, Type] = {p.name: p.type for p in symbol.parameters}

    return_stmt = node.body[0]
    assert isinstance(return_stmt, ast.Return)
    assert return_stmt.value is not None
    return_value = return_stmt.value

    value = _lower_expr(
        return_value, scope, symtab, source, diagnostics, enforce_definition_order=False
    )
    if value is None:
        return None
    if value.type != symbol.return_type:
        diagnostics.error(
            codes.TYPE_MISMATCH,
            f"function '{symbol.name}' is declared to return '{symbol.return_type}' "
            f"but returns '{value.type}'",
            _location(source, return_stmt),
        )
        return None

    ir_parameters = tuple(IRParameter(name=p.name, type=p.type) for p in symbol.parameters)
    return IRFunction(
        name=symbol.name,
        parameters=ir_parameters,
        return_type=symbol.return_type,
        body=(IRReturn(value=value, location=_location(source, return_stmt)),),
        location=symbol.location,
    )


def _lower_top_level_call(
    node: ast.Call,
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
) -> IRStmt | None:
    location = _location(source, node)
    assert isinstance(node.func, ast.Name)

    if node.func.id != _PRINT_BUILTIN:
        diagnostics.error(
            codes.UNKNOWN_CALL_TARGET,
            f"top-level statements may only call '{_PRINT_BUILTIN}' in this milestone",
            location,
        )
        return None

    args = _lower_call_arguments(
        node.args, {}, symtab, source, diagnostics, enforce_definition_order=True
    )
    if args is None:
        return None
    if not args:
        diagnostics.error(
            codes.ARGUMENT_COUNT_MISMATCH,
            "'print' requires at least one argument in this milestone",
            location,
        )
        return None
    for arg in args:
        if not isinstance(arg.type, IntType):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"'print' does not support values of type '{arg.type}' in this milestone",
                location,
            )
            return None

    return IRPrintStmt(args=tuple(args), location=location)


def _lower_call_arguments(
    arg_nodes: list[ast.expr],
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> list[IRExpr] | None:
    args: list[IRExpr] = []
    ok = True
    for arg_node in arg_nodes:
        lowered = _lower_expr(
            arg_node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if lowered is None:
            ok = False
        else:
            args.append(lowered)
    return args if ok else None


def _lower_call(
    node: ast.Call,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    assert isinstance(node.func, ast.Name)
    callee_name = node.func.id
    location = _location(source, node)

    if callee_name == _PRINT_BUILTIN:
        diagnostics.error(
            codes.TYPE_MISMATCH,
            "'print' does not return a usable value",
            location,
            help_text="'print' can only be used as a top-level statement in this milestone",
        )
        return None

    symbol = symtab.functions.get(callee_name)
    if symbol is None:
        diagnostics.error(
            codes.UNKNOWN_CALL_TARGET, f"call to unknown function '{callee_name}'", location
        )
        return None

    if enforce_definition_order and not symbol.location.line < location.line:
        diagnostics.error(
            codes.UNDEFINED_NAME,
            f"function '{callee_name}' is used here before it is defined",
            location,
            help_text=f"'{callee_name}' is defined at {symbol.location}",
        )
        return None

    args = _lower_call_arguments(
        node.args,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if args is None:
        return None

    if len(args) != symbol.arity:
        diagnostics.error(
            codes.ARGUMENT_COUNT_MISMATCH,
            f"'{callee_name}' takes {symbol.arity} argument(s) but {len(args)} were given",
            location,
        )
        return None

    for arg, parameter in zip(args, symbol.parameters, strict=True):
        if arg.type != parameter.type:
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"argument '{parameter.name}' of '{callee_name}' expects '{parameter.type}', "
                f"got '{arg.type}'",
                location,
            )
            return None

    return IRCall(callee=callee_name, args=tuple(args), type=symbol.return_type)


def _lower_expr(
    node: ast.expr,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    if isinstance(node, ast.Constant):
        assert isinstance(node.value, int) and not isinstance(node.value, bool)
        if not (_INT64_MIN <= node.value <= _INT64_MAX):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"integer literal {node.value} does not fit in a 64-bit int",
                _location(source, node),
                help_text="py2cpp represents Python's int as a 64-bit integer in this milestone",
            )
            return None
        return IRLiteral(value=node.value, type=IntType())

    if isinstance(node, ast.Name):
        declared = scope.get(node.id)
        if declared is None:
            diagnostics.error(
                codes.UNDEFINED_NAME, f"name '{node.id}' is not defined", _location(source, node)
            )
            return None
        return IRVarRef(name=node.id, type=declared)

    if isinstance(node, ast.BinOp):
        op = _BINOP_MAP[type(node.op)]
        left = _lower_expr(
            node.left,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        right = _lower_expr(
            node.right,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if left is None or right is None:
            return None
        if not isinstance(left.type, IntType) or not isinstance(right.type, IntType):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"unsupported operand types for '{type(node.op).__name__}': "
                f"'{left.type}' and '{right.type}'",
                _location(source, node),
            )
            return None
        return IRBinaryExpr(op=op, left=left, right=right, type=IntType())

    if isinstance(node, ast.Call):
        return _lower_call(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    raise AssertionError(  # pragma: no cover
        f"unexpected expression after subset validation: {node!r}"
    )
