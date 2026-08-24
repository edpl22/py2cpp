"""Lowers a validated Python AST into typed py2cpp IR.

This pass performs name resolution and type checking for expressions in
the same walk that builds IR nodes: for this milestone's grammar,
splitting those into separate tree-walks would just be near-identical
traversals of the same handful of node kinds. A dedicated flow-sensitive
types/infer.py stage is introduced once a future milestone's inference
needs genuinely outgrow this.

Scoping rule for local variables (a deliberate simplification, not an
oversight): a name's declaring assignment must occur at the same block
level as every place that later reads it. A variable first assigned
inside an if/elif/else or while/for body -- even in every branch -- does
not survive past that block; using it afterward is an undefined-name
error, the same as any other undeclared name. This sidesteps hoisting a
declaration out of branches with possibly different types (which C++,
unlike Python, cannot avoid: it requires one fixed declaration site).
Assigning an *already-declared* name from an outer scope is unaffected --
that's ordinary reassignment, and works from any nesting depth. Each
nested block gets its own copy of the enclosing scope specifically so
this falls out naturally, with no special hoisting logic required.

lower_module returns None once any diagnostic has been reported; callers
must not use a None result. It never raises for a user-error condition --
only ir.validate.InternalCompilerError, surfaced by the caller after
lowering, indicates a py2cpp bug.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.literals import extract_int_literal
from py2cpp.frontend.loader import SourceFile
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
    IRStringLiteral,
    IRToStr,
    IRTruthy,
    IRVarRef,
    IRWhile,
    LogicalOp,
)
from py2cpp.semantic.annotations import resolve_annotation
from py2cpp.semantic.symbols import FunctionSymbol, SymbolTable
from py2cpp.types.join import is_assignable, join
from py2cpp.types.model import BoolType, IntType, StringType, Type

_BINOP_MAP: dict[type[ast.operator], BinaryOp] = {
    ast.Add: BinaryOp.ADD,
    ast.Sub: BinaryOp.SUB,
    ast.Mult: BinaryOp.MUL,
}
_COMPARE_OP_MAP: dict[type[ast.cmpop], CompareOp] = {
    ast.Eq: CompareOp.EQ,
    ast.NotEq: CompareOp.NE,
    ast.Lt: CompareOp.LT,
    ast.LtE: CompareOp.LE,
    ast.Gt: CompareOp.GT,
    ast.GtE: CompareOp.GE,
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
    top_level_stmts: list[ast.stmt] = []

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
        else:
            top_level_stmts.append(stmt)

    main_body = _lower_block(
        top_level_stmts, {}, symtab, source, diagnostics, enforce_definition_order=True
    )

    if diagnostics.has_errors or main_body is None:
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

    return_stmt = node.body[-1]
    assert isinstance(return_stmt, ast.Return)
    assert return_stmt.value is not None

    leading = _lower_block(
        node.body[:-1], scope, symtab, source, diagnostics, enforce_definition_order=False
    )
    if leading is None:
        return None

    value = _lower_expr(
        return_stmt.value, scope, symtab, source, diagnostics, enforce_definition_order=False
    )
    if value is None:
        return None
    if not is_assignable(value.type, symbol.return_type):
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
        body=(*leading, IRReturn(value=value, location=_location(source, return_stmt))),
        location=symbol.location,
    )


def _lower_block(
    stmts: list[ast.stmt],
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> list[IRStmt] | None:
    result: list[IRStmt] = []
    ok = True
    for stmt in stmts:
        lowered = _lower_stmt(
            stmt,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if lowered is None:
            ok = False
        else:
            result.append(lowered)
    return result if ok else None


def _lower_stmt(
    stmt: ast.stmt,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRStmt | None:
    location = _location(source, stmt)

    if isinstance(stmt, ast.Assign):
        target = stmt.targets[0]
        assert isinstance(target, ast.Name)
        value = _lower_expr(
            stmt.value,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if value is None:
            return None
        return _finish_assign(target.id, value, None, scope, diagnostics, location)

    if isinstance(stmt, ast.AnnAssign):
        target = stmt.target
        assert isinstance(target, ast.Name)
        assert stmt.value is not None
        annotated_type = resolve_annotation(
            stmt.annotation, location, source, diagnostics, what=f"variable '{target.id}'"
        )
        value = _lower_expr(
            stmt.value,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if annotated_type is None or value is None:
            return None
        return _finish_assign(target.id, value, annotated_type, scope, diagnostics, location)

    if isinstance(stmt, ast.If):
        return _lower_if(
            stmt,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(stmt, ast.While):
        return _lower_while(
            stmt,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(stmt, ast.For):
        return _lower_for(
            stmt,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call_node = stmt.value
        assert isinstance(call_node.func, ast.Name)
        if call_node.func.id == _PRINT_BUILTIN:
            return _lower_print(
                call_node,
                scope,
                symtab,
                source,
                diagnostics,
                enforce_definition_order=enforce_definition_order,
            )
        call_expr = _lower_call(
            call_node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if call_expr is None:
            return None
        return IRExprStmt(expr=call_expr, location=location)

    raise AssertionError(
        f"unexpected statement after subset validation: {stmt!r}"
    )  # pragma: no cover


def _finish_assign(
    name: str,
    value: IRExpr,
    annotated_type: Type | None,
    scope: dict[str, Type],
    diagnostics: DiagnosticEngine,
    location: SourceLocation,
) -> IRAssign | None:
    existing = scope.get(name)

    if existing is None:
        target_type = annotated_type if annotated_type is not None else value.type
        if not is_assignable(value.type, target_type):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"cannot assign '{value.type}' to '{name}' of declared type '{target_type}'",
                location,
            )
            return None
        scope[name] = target_type
        return IRAssign(name=name, value=value, type=target_type, declare=True, location=location)

    if annotated_type is not None and annotated_type != existing:
        diagnostics.error(
            codes.TYPE_MISMATCH,
            f"'{name}' is already declared with type '{existing}'; cannot re-annotate as "
            f"'{annotated_type}'",
            location,
        )
        return None
    if not is_assignable(value.type, existing):
        diagnostics.error(
            codes.TYPE_MISMATCH,
            f"cannot assign '{value.type}' to '{name}', which already has type '{existing}'",
            location,
        )
        return None
    return IRAssign(name=name, value=value, type=existing, declare=False, location=location)


def _lower_condition(
    test: ast.expr,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    value = _lower_expr(
        test, scope, symtab, source, diagnostics, enforce_definition_order=enforce_definition_order
    )
    if value is None:
        return None
    if isinstance(value.type, BoolType):
        return value
    if isinstance(value.type, IntType):
        return IRTruthy(operand=value, type=BoolType())
    diagnostics.error(
        codes.TYPE_MISMATCH,
        f"condition must be 'bool' or 'int', got '{value.type}'",
        _location(source, test),
    )
    return None


def _lower_if(
    node: ast.If,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRIf | None:
    location = _location(source, node)
    condition = _lower_condition(
        node.test,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    then_body = _lower_block(
        node.body,
        dict(scope),
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    else_body = (
        _lower_block(
            node.orelse,
            dict(scope),
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if node.orelse
        else []
    )
    if condition is None or then_body is None or else_body is None:
        return None
    return IRIf(
        condition=condition,
        then_body=tuple(then_body),
        else_body=tuple(else_body),
        location=location,
    )


def _lower_while(
    node: ast.While,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRWhile | None:
    location = _location(source, node)
    condition = _lower_condition(
        node.test,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    body = _lower_block(
        node.body,
        dict(scope),
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if condition is None or body is None:
        return None
    return IRWhile(condition=condition, body=tuple(body), location=location)


def _lower_for(
    node: ast.For,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRFor | None:
    location = _location(source, node)
    assert isinstance(node.target, ast.Name)
    range_call = node.iter
    assert isinstance(range_call, ast.Call)
    args = range_call.args

    start_node: ast.expr | None
    if len(args) == 1:
        start_node, stop_node = None, args[0]
        step = 1
    elif len(args) == 2:
        start_node, stop_node = args[0], args[1]
        step = 1
    else:
        start_node, stop_node, step_node = args[0], args[1], args[2]
        step_literal = extract_int_literal(step_node)
        assert step_literal is not None
        step = step_literal

    if step == 0:
        diagnostics.error(codes.TYPE_MISMATCH, "'range' step must not be zero", location)
        return None

    start = (
        _lower_expr(
            start_node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if start_node is not None
        else IRLiteral(value=0, type=IntType())
    )
    stop = _lower_expr(
        stop_node,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if start is None or stop is None:
        return None
    if not isinstance(start.type, IntType) or not isinstance(stop.type, IntType):
        diagnostics.error(codes.TYPE_MISMATCH, "'range' arguments must be 'int'", location)
        return None

    loop_scope = dict(scope)
    loop_scope[node.target.id] = IntType()
    body = _lower_block(
        node.body,
        loop_scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if body is None:
        return None

    return IRFor(
        var=node.target.id, start=start, stop=stop, step=step, body=tuple(body), location=location
    )


def _lower_print(
    node: ast.Call,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRPrintStmt | None:
    location = _location(source, node)
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
    if not args:
        diagnostics.error(
            codes.ARGUMENT_COUNT_MISMATCH,
            "'print' requires at least one argument in this milestone",
            location,
        )
        return None
    for arg in args:
        if not isinstance(arg.type, (IntType, BoolType, StringType)):
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
            help_text="'print' can only be used as a statement in this milestone",
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
        if not is_assignable(arg.type, parameter.type):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"argument '{parameter.name}' of '{callee_name}' expects '{parameter.type}', "
                f"got '{arg.type}'",
                location,
            )
            return None

    return IRCall(callee=callee_name, args=tuple(args), type=symbol.return_type)


def _lower_fstring(
    node: ast.JoinedStr,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    parts: list[IRExpr] = []
    ok = True
    for value in node.values:
        if isinstance(value, ast.Constant):
            assert isinstance(value.value, str)
            parts.append(IRStringLiteral(value=value.value, type=StringType()))
            continue

        assert isinstance(value, ast.FormattedValue)
        inner = _lower_expr(
            value.value,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if inner is None:
            ok = False
            continue
        if not isinstance(inner.type, (IntType, BoolType, StringType)):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"f-string does not support values of type '{inner.type}' in this milestone",
                _location(source, value.value),
            )
            ok = False
            continue
        if isinstance(inner.type, StringType):
            parts.append(inner)
        else:
            parts.append(IRToStr(operand=inner, type=StringType()))

    if not ok:
        return None
    if not parts:
        return IRStringLiteral(value="", type=StringType())

    result = parts[0]
    for part in parts[1:]:
        result = IRBinaryExpr(op=BinaryOp.ADD, left=result, right=part, type=StringType())
    return result


def _lower_expr(
    node: ast.expr,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    literal_value = extract_int_literal(node)
    if literal_value is not None:
        if not (_INT64_MIN <= literal_value <= _INT64_MAX):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"integer literal {literal_value} does not fit in a 64-bit int",
                _location(source, node),
                help_text="py2cpp represents Python's int as a 64-bit integer in this milestone",
            )
            return None
        return IRLiteral(value=literal_value, type=IntType())

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return IRStringLiteral(value=node.value, type=StringType())

    if isinstance(node, ast.JoinedStr):
        return _lower_fstring(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

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
        # '+' between two strings is concatenation, not arithmetic; str
        # doesn't support '-'/'*' (falls through to the int check below,
        # which rejects it with a clear diagnostic).
        if (
            op is BinaryOp.ADD
            and isinstance(left.type, StringType)
            and isinstance(right.type, StringType)
        ):
            return IRBinaryExpr(op=BinaryOp.ADD, left=left, right=right, type=StringType())
        # bool operands auto-convert to int here (both C++ and this
        # project's join rules treat bool as an int subtype), so a
        # comparison result like '(a > 0)' can be summed directly.
        if not is_assignable(left.type, IntType()) or not is_assignable(right.type, IntType()):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"unsupported operand types for '{type(node.op).__name__}': "
                f"'{left.type}' and '{right.type}'",
                _location(source, node),
            )
            return None
        return IRBinaryExpr(op=op, left=left, right=right, type=IntType())

    if isinstance(node, ast.Compare):
        compare_op = _COMPARE_OP_MAP[type(node.ops[0])]
        left = _lower_expr(
            node.left,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        right = _lower_expr(
            node.comparators[0],
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if left is None or right is None:
            return None
        if join(left.type, right.type) is None:
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"cannot compare '{left.type}' and '{right.type}'",
                _location(source, node),
            )
            return None
        return IRCompare(op=compare_op, left=left, right=right, type=BoolType())

    if isinstance(node, ast.BoolOp):
        logical_op = LogicalOp.AND if isinstance(node.op, ast.And) else LogicalOp.OR
        keyword = "and" if logical_op is LogicalOp.AND else "or"
        operands: list[IRExpr] = []
        ok = True
        for value_node in node.values:
            lowered = _lower_expr(
                value_node,
                scope,
                symtab,
                source,
                diagnostics,
                enforce_definition_order=enforce_definition_order,
            )
            if lowered is None:
                ok = False
                continue
            if not isinstance(lowered.type, BoolType):
                diagnostics.error(
                    codes.TYPE_MISMATCH,
                    f"'{keyword}' requires 'bool' operands in this milestone, got '{lowered.type}'",
                    _location(source, value_node),
                    help_text="comparisons (e.g. 'a < b') produce bool",
                )
                ok = False
                continue
            operands.append(lowered)
        if not ok:
            return None
        result = operands[0]
        for operand in operands[1:]:
            result = IRLogicalExpr(op=logical_op, left=result, right=operand, type=BoolType())
        return result

    if isinstance(node, ast.UnaryOp):
        assert isinstance(node.op, ast.Not)
        not_operand = _lower_expr(
            node.operand,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if not_operand is None:
            return None
        if not isinstance(not_operand.type, BoolType):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"'not' requires a 'bool' operand in this milestone, got '{not_operand.type}'",
                _location(source, node),
                help_text="comparisons (e.g. 'a < b') produce bool",
            )
            return None
        return IRNot(operand=not_operand, type=BoolType())

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
