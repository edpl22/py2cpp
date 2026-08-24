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
    IRAttribute,
    IRAttributeAccess,
    IRAttributeAssign,
    IRBinaryExpr,
    IRCall,
    IRClassDef,
    IRCompare,
    IRConstruct,
    IRConstructor,
    IRDictLiteral,
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
    IRReturn,
    IRSetLiteral,
    IRStmt,
    IRStringLiteral,
    IRToStr,
    IRTruthy,
    IRTupleIndex,
    IRTupleLiteral,
    IRVarRef,
    IRWhile,
    LogicalOp,
)
from py2cpp.semantic.annotations import resolve_annotation
from py2cpp.semantic.symbols import (
    AttributeSymbol,
    ClassSymbol,
    FunctionSymbol,
    MethodSymbol,
    ParameterSymbol,
    SymbolTable,
)
from py2cpp.types.join import is_assignable, join
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
_SELF = "self"
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def lower_module(
    tree: ast.Module,
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
) -> IRModule | None:
    virtual_methods, override_methods = _compute_virtual_methods(symtab)

    classes: list[IRClassDef] = []
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
        elif isinstance(stmt, ast.ClassDef):
            class_symbol = symtab.classes.get(stmt.name)
            if class_symbol is None or class_symbol.location != _location(source, stmt):
                continue
            class_def = _lower_class(
                stmt,
                class_symbol,
                symtab,
                source,
                diagnostics,
                virtual_methods=virtual_methods,
                override_methods=override_methods,
            )
            if class_def is not None:
                classes.append(class_def)
        else:
            top_level_stmts.append(stmt)

    main_body = _lower_block(
        top_level_stmts, {}, symtab, source, diagnostics, enforce_definition_order=True
    )

    if diagnostics.has_errors or main_body is None:
        return None
    return IRModule(
        name=source.path.stem,
        classes=tuple(classes),
        functions=tuple(functions),
        main_body=tuple(main_body),
    )


def _compute_virtual_methods(
    symtab: SymbolTable,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Decision D: a method is virtual iff it's actually overridden
    somewhere in the whole compiled program (closed-world, computed --
    never user-declared). For each class's own method, walk up its base
    chain for the nearest ancestor that also directly defines the same
    name; if found, both ends of that pair are virtual, and the subclass's
    definition is an override. Chains longer than one link fall out for
    free, since each adjacent pair in the chain gets marked this way.
    """

    virtual: set[tuple[str, str]] = set()
    override: set[tuple[str, str]] = set()
    for name, symbol in symtab.classes.items():
        for method_name in symbol.methods:
            current = symbol.base
            while current is not None:
                ancestor = symtab.classes[current]
                if method_name in ancestor.methods:
                    virtual.add((current, method_name))
                    virtual.add((name, method_name))
                    override.add((name, method_name))
                    break
                current = ancestor.base
    return virtual, override


def _is_subclass(name: str, ancestor: str, symtab: SymbolTable) -> bool:
    current: str | None = name
    while current is not None:
        if current == ancestor:
            return True
        current = symtab.classes[current].base
    return False


def _assignable(value_type: Type, target_type: Type, symtab: SymbolTable) -> bool:
    """Like types.join.is_assignable, extended with class-hierarchy
    awareness: a derived-class value may be assigned/passed where its base
    class is expected (the polymorphism this milestone commits to). The
    pure types/ layer stays hierarchy-agnostic; this is the one place that
    composes primitive coercion rules with class subtyping, matching this
    module's own role as "combined name-resolution + type-check + IR
    build".
    """

    if is_assignable(value_type, target_type):
        return True
    if isinstance(value_type, ClassType) and isinstance(target_type, ClassType):
        return _is_subclass(value_type.name, target_type.name, symtab)
    return False


def _resolve_attribute(class_name: str, attr: str, symtab: SymbolTable) -> AttributeSymbol | None:
    current: str | None = class_name
    while current is not None:
        class_symbol = symtab.classes[current]
        if attr in class_symbol.attributes:
            return class_symbol.attributes[attr]
        current = class_symbol.base
    return None


def _resolve_method(class_name: str, method: str, symtab: SymbolTable) -> MethodSymbol | None:
    current: str | None = class_name
    while current is not None:
        class_symbol = symtab.classes[current]
        if method in class_symbol.methods:
            return class_symbol.methods[method]
        current = class_symbol.base
    return None


def _typecheck_arguments(
    args: list[IRExpr],
    parameters: tuple[ParameterSymbol, ...],
    owner_name: str,
    symtab: SymbolTable,
    diagnostics: DiagnosticEngine,
    location: SourceLocation,
) -> bool:
    if len(args) != len(parameters):
        diagnostics.error(
            codes.ARGUMENT_COUNT_MISMATCH,
            f"'{owner_name}' takes {len(parameters)} argument(s) but {len(args)} were given",
            location,
        )
        return False
    for arg, parameter in zip(args, parameters, strict=True):
        if not _assignable(arg.type, parameter.type, symtab):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"argument '{parameter.name}' of '{owner_name}' expects '{parameter.type}', "
                f"got '{arg.type}'",
                location,
            )
            return False
    return True


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
    if not _assignable(value.type, symbol.return_type, symtab):
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


def _lower_class(
    node: ast.ClassDef,
    class_symbol: ClassSymbol,
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    virtual_methods: set[tuple[str, str]],
    override_methods: set[tuple[str, str]],
) -> IRClassDef | None:
    init_node = next(
        stmt
        for stmt in node.body
        if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__"
    )
    constructor = _lower_constructor(init_node, class_symbol, symtab, source, diagnostics)

    ok = constructor is not None
    methods: list[IRMethod] = []
    for stmt in node.body:
        if not isinstance(stmt, ast.FunctionDef) or stmt.name == "__init__":
            continue
        method_symbol = class_symbol.methods.get(stmt.name)
        if method_symbol is None or method_symbol.location != _location(source, stmt):
            continue
        method = _lower_method(
            stmt,
            class_symbol,
            method_symbol,
            is_virtual=(class_symbol.name, stmt.name) in virtual_methods,
            is_override=(class_symbol.name, stmt.name) in override_methods,
            symtab=symtab,
            source=source,
            diagnostics=diagnostics,
        )
        if method is None:
            ok = False
            continue
        methods.append(method)

    if not ok or constructor is None:
        return None

    is_base_of_something = any(s.base == class_symbol.name for s in symtab.classes.values())
    ir_attributes = tuple(
        IRAttribute(name=attr.name, type=attr.type) for attr in class_symbol.attributes.values()
    )
    return IRClassDef(
        name=class_symbol.name,
        base=class_symbol.base,
        attributes=ir_attributes,
        constructor=constructor,
        methods=tuple(methods),
        needs_virtual_destructor=is_base_of_something or class_symbol.base is not None,
        location=class_symbol.location,
    )


def _lower_constructor(
    init_node: ast.FunctionDef,
    class_symbol: ClassSymbol,
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
) -> IRConstructor | None:
    location = _location(source, init_node)
    scope: dict[str, Type] = {_SELF: ClassType(class_symbol.name)}
    for p in class_symbol.init_parameters:
        scope[p.name] = p.type

    body = init_node.body
    base_args: tuple[IRExpr, ...] | None = None
    start = 0
    if class_symbol.base is not None:
        first = body[0]
        assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
        super_call = first.value
        args = _lower_call_arguments(
            super_call.args, scope, symtab, source, diagnostics, enforce_definition_order=False
        )
        if args is None:
            return None
        base_symbol = symtab.classes[class_symbol.base]
        if not _typecheck_arguments(
            args,
            base_symbol.init_parameters,
            f"{class_symbol.base}.__init__",
            symtab,
            diagnostics,
            _location(source, super_call),
        ):
            return None
        base_args = tuple(args)
        start = 1

    ir_body = _lower_block(
        body[start:], scope, symtab, source, diagnostics, enforce_definition_order=False
    )
    if ir_body is None:
        return None

    ir_parameters = tuple(
        IRParameter(name=p.name, type=p.type) for p in class_symbol.init_parameters
    )
    return IRConstructor(
        parameters=ir_parameters, base_args=base_args, body=tuple(ir_body), location=location
    )


def _lower_method(
    node: ast.FunctionDef,
    class_symbol: ClassSymbol,
    method_symbol: MethodSymbol,
    *,
    is_virtual: bool,
    is_override: bool,
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
) -> IRMethod | None:
    scope: dict[str, Type] = {_SELF: ClassType(class_symbol.name)}
    for p in method_symbol.parameters:
        scope[p.name] = p.type

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
    if not _assignable(value.type, method_symbol.return_type, symtab):
        diagnostics.error(
            codes.TYPE_MISMATCH,
            f"method '{class_symbol.name}.{method_symbol.name}' is declared to return "
            f"'{method_symbol.return_type}' but returns '{value.type}'",
            _location(source, return_stmt),
        )
        return None

    ir_parameters = tuple(IRParameter(name=p.name, type=p.type) for p in method_symbol.parameters)
    return IRMethod(
        name=method_symbol.name,
        parameters=ir_parameters,
        return_type=method_symbol.return_type,
        body=(*leading, IRReturn(value=value, location=_location(source, return_stmt))),
        is_virtual=is_virtual,
        is_override=is_override,
        location=method_symbol.location,
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
        if isinstance(stmt, ast.Pass):
            continue
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
        if isinstance(target, ast.Attribute):
            return _lower_attribute_assign(
                target,
                stmt.value,
                scope,
                symtab,
                source,
                diagnostics,
                location,
                enforce_definition_order=enforce_definition_order,
            )
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
        return _finish_assign(target.id, value, None, scope, symtab, diagnostics, location)

    if isinstance(stmt, ast.AnnAssign):
        target = stmt.target
        assert stmt.value is not None
        if isinstance(target, ast.Attribute):
            # Subset validation guarantees this is 'self.<attr>: T = value'
            # as a direct top-level statement of '__init__' -- the
            # attribute already exists in the symbol table by this point
            # (collect.py built it from this exact AnnAssign), so there's
            # nothing left to re-resolve here beyond the usual assignment
            # type check that _lower_attribute_assign already does.
            return _lower_attribute_assign(
                target,
                stmt.value,
                scope,
                symtab,
                source,
                diagnostics,
                location,
                enforce_definition_order=enforce_definition_order,
            )
        assert isinstance(target, ast.Name)
        annotated_type = resolve_annotation(
            stmt.annotation,
            location,
            source,
            diagnostics,
            what=f"variable '{target.id}'",
            known_classes=frozenset(symtab.classes),
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
        return _finish_assign(
            target.id, value, annotated_type, scope, symtab, diagnostics, location
        )

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
        if isinstance(call_node.func, ast.Name) and call_node.func.id == _PRINT_BUILTIN:
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


def _lower_attribute_target(
    target: ast.Attribute,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> tuple[IRExpr, Type] | None:
    """Lowers the object expression of an 'obj.attr' target (assignment or
    read) and resolves 'attr''s declared type, walking obj's class up its
    base chain. Shared by attribute reads (_lower_expr) and attribute
    assignment (_lower_attribute_assign), since both need exactly this.
    """

    obj = _lower_expr(
        target.value,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if obj is None:
        return None
    if not isinstance(obj.type, ClassType):
        diagnostics.error(
            codes.TYPE_MISMATCH,
            f"'{obj.type}' has no attributes (it is not a class instance)",
            _location(source, target),
        )
        return None
    attr_symbol = _resolve_attribute(obj.type.name, target.attr, symtab)
    if attr_symbol is None:
        diagnostics.error(
            codes.UNDEFINED_NAME,
            f"'{obj.type.name}' has no attribute '{target.attr}'",
            _location(source, target),
        )
        return None
    return obj, attr_symbol.type


def _lower_attribute_assign(
    target: ast.Attribute,
    value_node: ast.expr,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    location: SourceLocation,
    *,
    enforce_definition_order: bool,
) -> IRAttributeAssign | None:
    resolved = _lower_attribute_target(
        target,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if resolved is None:
        return None
    obj, attr_type = resolved
    value = _lower_expr(
        value_node,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if value is None:
        return None
    if not _assignable(value.type, attr_type, symtab):
        diagnostics.error(
            codes.TYPE_MISMATCH,
            f"cannot assign '{value.type}' to attribute '{target.attr}' of declared type "
            f"'{attr_type}'",
            location,
        )
        return None
    return IRAttributeAssign(
        obj=obj, attr=target.attr, value=value, type=attr_type, location=location
    )


def _finish_assign(
    name: str,
    value: IRExpr,
    annotated_type: Type | None,
    scope: dict[str, Type],
    symtab: SymbolTable,
    diagnostics: DiagnosticEngine,
    location: SourceLocation,
) -> IRAssign | None:
    existing = scope.get(name)

    if existing is None:
        target_type = annotated_type if annotated_type is not None else value.type
        if not _assignable(value.type, target_type, symtab):
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
    if not _assignable(value.type, existing, symtab):
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


def _is_range_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
    )


def _parse_range_call(
    range_call: ast.Call,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
    location: SourceLocation,
) -> tuple[IRExpr, IRExpr, int] | None:
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
    return start, stop, step


def _iterable_element_type(
    container_type: Type, location: SourceLocation, diagnostics: DiagnosticEngine
) -> Type | None:
    if isinstance(container_type, (ListType, SetType)):
        return container_type.element_type
    if isinstance(container_type, DictType):
        # Python 'for k in d' iterates keys only.
        return container_type.key_type
    if isinstance(container_type, TupleType):
        diagnostics.error(
            codes.TYPE_MISMATCH,
            "iterating a 'tuple' is not supported in this milestone",
            location,
            help_text="index its elements directly, e.g. 't[0]'",
        )
        return None
    diagnostics.error(
        codes.TYPE_MISMATCH,
        f"'{container_type}' object is not iterable in this milestone",
        location,
    )
    return None


def _lower_for(
    node: ast.For,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRFor | IRForEach | None:
    location = _location(source, node)
    assert isinstance(node.target, ast.Name)

    if _is_range_call(node.iter):
        assert isinstance(node.iter, ast.Call)
        parsed = _parse_range_call(
            node.iter,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
            location=location,
        )
        if parsed is None:
            return None
        start, stop, step = parsed
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
            var=node.target.id,
            start=start,
            stop=stop,
            step=step,
            body=tuple(body),
            location=location,
        )

    iterable = _lower_expr(
        node.iter,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if iterable is None:
        return None
    element_type = _iterable_element_type(iterable.type, location, diagnostics)
    if element_type is None:
        return None
    loop_scope = dict(scope)
    loop_scope[node.target.id] = element_type
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
    return IRForEach(
        var=node.target.id,
        var_type=element_type,
        iterable=iterable,
        body=tuple(body),
        location=location,
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
        if not isinstance(
            arg.type, (IntType, BoolType, StringType, ListType, DictType, SetType, TupleType)
        ):
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
    if isinstance(node.func, ast.Attribute):
        return _lower_method_call(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

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

    if callee_name in symtab.classes:
        return _lower_construct(
            node,
            callee_name,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    symbol = symtab.functions.get(callee_name)
    if symbol is None:
        diagnostics.error(
            codes.UNKNOWN_CALL_TARGET,
            f"call to unknown function or class '{callee_name}'",
            location,
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

    if not _typecheck_arguments(
        args, symbol.parameters, callee_name, symtab, diagnostics, location
    ):
        return None

    return IRCall(callee=callee_name, args=tuple(args), type=symbol.return_type)


def _lower_construct(
    node: ast.Call,
    class_name: str,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    location = _location(source, node)
    class_symbol = symtab.classes[class_name]

    if enforce_definition_order and not class_symbol.location.line < location.line:
        diagnostics.error(
            codes.UNDEFINED_NAME,
            f"class '{class_name}' is used here before it is defined",
            location,
            help_text=f"'{class_name}' is defined at {class_symbol.location}",
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

    if not _typecheck_arguments(
        args, class_symbol.init_parameters, f"{class_name}(...)", symtab, diagnostics, location
    ):
        return None

    return IRConstruct(class_name=class_name, args=tuple(args), type=ClassType(class_name))


def _lower_method_call(
    node: ast.Call,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    assert isinstance(node.func, ast.Attribute)
    location = _location(source, node)

    obj = _lower_expr(
        node.func.value,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if obj is None:
        return None
    if not isinstance(obj.type, ClassType):
        diagnostics.error(
            codes.TYPE_MISMATCH,
            f"'{obj.type}' has no methods (it is not a class instance)",
            location,
        )
        return None

    method_name = node.func.attr
    method_symbol = _resolve_method(obj.type.name, method_name, symtab)
    if method_symbol is None:
        diagnostics.error(
            codes.UNDEFINED_NAME,
            f"'{obj.type.name}' has no method '{method_name}'",
            location,
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

    owner_name = f"{obj.type.name}.{method_name}"
    if not _typecheck_arguments(
        args, method_symbol.parameters, owner_name, symtab, diagnostics, location
    ):
        return None

    return IRMethodCall(
        obj=obj, method=method_name, args=tuple(args), type=method_symbol.return_type
    )


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


def _join_all(types: list[Type]) -> Type | None:
    """Folds join() across every element type of a non-empty literal (the
    subset validator rejects empty list/dict/set literals, so 'types' is
    never empty here).
    """

    result = types[0]
    for t in types[1:]:
        joined = join(result, t)
        if joined is None:
            return None
        result = joined
    return result


def _lower_list_literal(
    node: ast.List,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    elements = _lower_call_arguments(
        node.elts,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if elements is None:
        return None
    element_type = _join_all([e.type for e in elements])
    if element_type is None:
        diagnostics.error(
            codes.TYPE_MISMATCH,
            "list literal elements must all share a common type in this milestone",
            _location(source, node),
        )
        return None
    return IRListLiteral(elements=tuple(elements), type=ListType(element_type))


def _lower_set_literal(
    node: ast.Set,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    elements = _lower_call_arguments(
        node.elts,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if elements is None:
        return None
    element_type = _join_all([e.type for e in elements])
    if element_type is None:
        diagnostics.error(
            codes.TYPE_MISMATCH,
            "set literal elements must all share a common type in this milestone",
            _location(source, node),
        )
        return None
    return IRSetLiteral(elements=tuple(elements), type=SetType(element_type))


def _lower_dict_literal(
    node: ast.Dict,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    keys: list[IRExpr] = []
    values: list[IRExpr] = []
    ok = True
    for key_node, value_node in zip(node.keys, node.values, strict=True):
        # The subset validator rejects '**' unpacking (a None key), so
        # every key here is a real expression.
        assert key_node is not None
        key = _lower_expr(
            key_node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        value = _lower_expr(
            value_node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if key is None or value is None:
            ok = False
            continue
        keys.append(key)
        values.append(value)
    if not ok:
        return None

    location = _location(source, node)
    key_type = _join_all([k.type for k in keys])
    if key_type is None:
        diagnostics.error(
            codes.TYPE_MISMATCH,
            "dict literal keys must all share a common type in this milestone",
            location,
        )
        return None
    value_type = _join_all([v.type for v in values])
    if value_type is None:
        diagnostics.error(
            codes.TYPE_MISMATCH,
            "dict literal values must all share a common type in this milestone",
            location,
        )
        return None
    return IRDictLiteral(
        keys=tuple(keys), values=tuple(values), type=DictType(key_type, value_type)
    )


def _lower_tuple_literal(
    node: ast.Tuple,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    elements = _lower_call_arguments(
        node.elts,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if elements is None:
        return None
    return IRTupleLiteral(
        elements=tuple(elements), type=TupleType(tuple(e.type for e in elements))
    )


def _lower_subscript(
    node: ast.Subscript,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    container = _lower_expr(
        node.value,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if container is None:
        return None
    location = _location(source, node)
    container_type = container.type

    if isinstance(container_type, ListType):
        index = _lower_expr(
            node.slice,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if index is None:
            return None
        if not is_assignable(index.type, IntType()):
            diagnostics.error(
                codes.TYPE_MISMATCH, f"list index must be 'int', got '{index.type}'", location
            )
            return None
        return IRIndex(container=container, index=index, type=container_type.element_type)

    if isinstance(container_type, DictType):
        index = _lower_expr(
            node.slice,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if index is None:
            return None
        if not is_assignable(index.type, container_type.key_type):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"dict key must be '{container_type.key_type}', got '{index.type}'",
                location,
            )
            return None
        return IRIndex(container=container, index=index, type=container_type.value_type)

    if isinstance(container_type, TupleType):
        literal_index = extract_int_literal(node.slice)
        if literal_index is None:
            diagnostics.error(
                codes.TYPE_MISMATCH,
                "tuple index must be a compile-time integer literal in this milestone",
                location,
                help_text="a runtime-computed tuple index arrives in a later milestone",
            )
            return None
        length = len(container_type.element_types)
        resolved = literal_index + length if literal_index < 0 else literal_index
        if resolved < 0 or resolved >= length:
            diagnostics.error(
                codes.TYPE_MISMATCH,
                f"tuple index {literal_index} is out of range for a tuple of length {length}",
                location,
            )
            return None
        return IRTupleIndex(
            tuple_expr=container, index=resolved, type=container_type.element_types[resolved]
        )

    diagnostics.error(
        codes.TYPE_MISMATCH,
        f"'{container_type}' object is not subscriptable in this milestone",
        location,
    )
    return None


def _lower_comprehension(
    node: ast.ListComp,
    scope: dict[str, Type],
    symtab: SymbolTable,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    enforce_definition_order: bool,
) -> IRExpr | None:
    location = _location(source, node)
    generator = node.generators[0]
    assert isinstance(generator.target, ast.Name)
    var = generator.target.id

    if _is_range_call(generator.iter):
        assert isinstance(generator.iter, ast.Call)
        parsed = _parse_range_call(
            generator.iter,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
            location=location,
        )
        if parsed is None:
            return None
        start, stop, step = parsed
        comp_scope = dict(scope)
        comp_scope[var] = IntType()
        condition: IRExpr | None = None
        if generator.ifs:
            condition = _lower_condition(
                generator.ifs[0],
                comp_scope,
                symtab,
                source,
                diagnostics,
                enforce_definition_order=enforce_definition_order,
            )
            if condition is None:
                return None
        element = _lower_expr(
            node.elt,
            comp_scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if element is None:
            return None
        return IRListCompRange(
            element=element,
            var=var,
            start=start,
            stop=stop,
            step=step,
            condition=condition,
            type=ListType(element.type),
        )

    iterable = _lower_expr(
        generator.iter,
        scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if iterable is None:
        return None
    element_type = _iterable_element_type(iterable.type, location, diagnostics)
    if element_type is None:
        return None
    comp_scope = dict(scope)
    comp_scope[var] = element_type
    condition = None
    if generator.ifs:
        condition = _lower_condition(
            generator.ifs[0],
            comp_scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if condition is None:
            return None
    element = _lower_expr(
        node.elt,
        comp_scope,
        symtab,
        source,
        diagnostics,
        enforce_definition_order=enforce_definition_order,
    )
    if element is None:
        return None
    return IRListCompForEach(
        element=element,
        var=var,
        var_type=element_type,
        iterable=iterable,
        condition=condition,
        type=ListType(element.type),
    )


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

    if isinstance(node, ast.List):
        return _lower_list_literal(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(node, ast.Set):
        return _lower_set_literal(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(node, ast.Dict):
        return _lower_dict_literal(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(node, ast.Tuple):
        return _lower_tuple_literal(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(node, ast.Subscript):
        return _lower_subscript(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )

    if isinstance(node, ast.ListComp):
        return _lower_comprehension(
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

    if isinstance(node, ast.Attribute):
        resolved = _lower_attribute_target(
            node,
            scope,
            symtab,
            source,
            diagnostics,
            enforce_definition_order=enforce_definition_order,
        )
        if resolved is None:
            return None
        obj, attr_type = resolved
        return IRAttributeAccess(obj=obj, attr=node.attr, type=attr_type)

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
        # Comparing class instances needs '__eq__'/'__lt__'-style dunder
        # support, which this milestone doesn't have; join() would let two
        # same-named ClassTypes through by plain equality (they're a valid
        # 'type', just not a supported comparison), so that's rejected
        # explicitly rather than silently falling through to it.
        if isinstance(left.type, ClassType) or isinstance(right.type, ClassType):
            diagnostics.error(
                codes.TYPE_MISMATCH,
                "comparing class instances is not supported in this milestone",
                _location(source, node),
                help_text="operator-overload dunders like '__eq__' arrive in a later milestone",
            )
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
