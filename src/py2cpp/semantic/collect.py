"""Builds the module symbol table from function and class definitions,
resolving each parameter's, return value's, and attribute's type
annotation along the way.

Symbol-table construction is kept separate from expression-level name
resolution and type checking (see ir/lower.py): the table it produces is a
shared artifact both that pass and the backend rely on.

Class names are gathered in a first pass over the module, before any
annotation is resolved, so a class's own methods/attributes may reference
that class (or another class defined later in the file) in a type
annotation -- this matches real Python, where an annotation on a 'self.x'
assignment is only evaluated when the method actually runs, by which time
the whole module has already finished executing. Base-class references and
object-construction calls are a different question -- those need the named
class to actually exist yet, exactly like calling a function -- so base
classes are required to be defined earlier in the file (checked here,
since it's needed to emit the base class's C++ declaration first) and
constructor calls are order-checked at their use site in ir/lower.py,
mirroring how ordinary function calls are already order-checked there.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.loader import SourceFile
from py2cpp.semantic.annotations import resolve_annotation
from py2cpp.semantic.exceptions import is_known_exception
from py2cpp.semantic.symbols import (
    AttributeSymbol,
    ClassSymbol,
    FunctionSymbol,
    MethodSymbol,
    ParameterSymbol,
    SymbolTable,
)

_SELF = "self"


def collect_symbols(
    tree: ast.Module, source: SourceFile, diagnostics: DiagnosticEngine
) -> SymbolTable:
    table = SymbolTable()
    known_classes = frozenset(
        stmt.name for stmt in tree.body if isinstance(stmt, ast.ClassDef)
    )
    defined_names: dict[str, SourceLocation] = {}

    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef):
            symbol = _collect_function(stmt, source, diagnostics, known_classes=known_classes)
            if symbol is None:
                continue
            if not _claim_name(symbol.name, symbol.location, defined_names, diagnostics):
                continue
            table.functions[symbol.name] = symbol
        elif isinstance(stmt, ast.ClassDef):
            class_symbol = _collect_class(
                stmt, source, diagnostics, known_classes=known_classes, classes=table.classes
            )
            if class_symbol is None:
                continue
            if not _claim_name(
                class_symbol.name, class_symbol.location, defined_names, diagnostics
            ):
                continue
            table.classes[class_symbol.name] = class_symbol

    return table


def _claim_name(
    name: str,
    location: SourceLocation,
    defined_names: dict[str, SourceLocation],
    diagnostics: DiagnosticEngine,
) -> bool:
    if is_known_exception(name):
        diagnostics.error(
            codes.DUPLICATE_DEFINITION,
            f"'{name}' is a reserved built-in exception type name and can't be redefined",
            location,
        )
        return False
    existing = defined_names.get(name)
    if existing is not None:
        diagnostics.error(
            codes.DUPLICATE_DEFINITION,
            f"'{name}' is already defined",
            location,
            help_text=f"the previous definition is at {existing}",
        )
        return False
    defined_names[name] = location
    return True


def _location(source: SourceFile, node: ast.AST) -> SourceLocation:
    return SourceLocation(
        filename=source.path,
        line=getattr(node, "lineno", 1),
        column=getattr(node, "col_offset", 0) + 1,
    )


def _collect_parameters(
    args: ast.arguments,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    known_classes: frozenset[str],
    skip_self: bool,
    owner: str,
) -> list[ParameterSymbol] | None:
    ok = True
    raw_args = args.args
    if skip_self:
        raw_args = raw_args[1:]

    parameters: list[ParameterSymbol] = []
    for arg in raw_args:
        arg_location = _location(source, arg)
        arg_type = resolve_annotation(
            arg.annotation,
            arg_location,
            source,
            diagnostics,
            what=f"parameter '{arg.arg}' of '{owner}'",
            known_classes=known_classes,
        )
        if arg_type is None:
            ok = False
            continue
        parameters.append(ParameterSymbol(name=arg.arg, type=arg_type, location=arg_location))

    return parameters if ok else None


def _collect_function(
    node: ast.FunctionDef,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    known_classes: frozenset[str],
) -> FunctionSymbol | None:
    location = _location(source, node)
    parameters = _collect_parameters(
        node.args,
        source,
        diagnostics,
        known_classes=known_classes,
        skip_self=False,
        owner=node.name,
    )
    return_type = resolve_annotation(
        node.returns,
        location,
        source,
        diagnostics,
        what=f"function '{node.name}'s return value",
        known_classes=known_classes,
    )

    if parameters is None or return_type is None:
        return None
    return FunctionSymbol(
        name=node.name, parameters=tuple(parameters), return_type=return_type, location=location
    )


def _collect_class(
    node: ast.ClassDef,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    known_classes: frozenset[str],
    classes: dict[str, ClassSymbol],
) -> ClassSymbol | None:
    location = _location(source, node)

    base: str | None = None
    if node.bases:
        base_node = node.bases[0]
        assert isinstance(base_node, ast.Name)
        base = base_node.id
        if base not in classes:
            diagnostics.error(
                codes.UNDEFINED_NAME,
                f"base class '{base}' is used here before it is defined",
                _location(source, base_node),
                help_text=f"'{base}' must be defined earlier in the file to be used as a base "
                "class",
            )
            return None

    init_node = next(
        (
            stmt
            for stmt in node.body
            if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__"
        ),
        None,
    )
    if init_node is None:
        diagnostics.error(
            codes.MISSING_ANNOTATION,
            f"class '{node.name}' must define an '__init__' method in this milestone",
            location,
            help_text="every class needs its own '__init__'; constructors are not inherited yet",
        )
        return None

    ok = True
    parameters = _collect_parameters(
        init_node.args,
        source,
        diagnostics,
        known_classes=known_classes,
        skip_self=True,
        owner=f"{node.name}.__init__",
    )
    if parameters is None:
        ok = False
        parameters = []

    inherited_attrs = _inherited_attributes(base, classes)
    attributes = _collect_attributes(
        init_node, node.name, source, diagnostics, known_classes=known_classes,
        inherited=inherited_attrs,
    )
    if attributes is None:
        ok = False
        attributes = {}

    methods: dict[str, MethodSymbol] = {}
    for stmt in node.body:
        if not isinstance(stmt, ast.FunctionDef) or stmt.name == "__init__":
            continue
        method = _collect_method(stmt, node.name, source, diagnostics, known_classes=known_classes)
        if method is None:
            ok = False
            continue
        if method.name in methods:
            diagnostics.error(
                codes.DUPLICATE_DEFINITION,
                f"method '{method.name}' is already defined on class '{node.name}'",
                method.location,
                help_text=f"the previous definition is at {methods[method.name].location}",
            )
            ok = False
            continue
        methods[method.name] = method

    if not ok:
        return None
    return ClassSymbol(
        name=node.name,
        base=base,
        init_parameters=tuple(parameters),
        attributes=attributes,
        methods=methods,
        location=location,
    )


def _inherited_attributes(
    base: str | None, classes: dict[str, ClassSymbol]
) -> dict[str, AttributeSymbol]:
    result: dict[str, AttributeSymbol] = {}
    current = base
    while current is not None:
        symbol = classes[current]
        for name, attr in symbol.attributes.items():
            result.setdefault(name, attr)
        current = symbol.base
    return result


def _collect_attributes(
    init_node: ast.FunctionDef,
    class_name: str,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    known_classes: frozenset[str],
    inherited: dict[str, AttributeSymbol],
) -> dict[str, AttributeSymbol] | None:
    ok = True
    attributes: dict[str, AttributeSymbol] = {}
    # Subset validation already guarantees every attribute-declaring
    # AnnAssign is a direct, unconditional top-level statement of
    # '__init__' (never nested in an if/while/for) -- so only the body's
    # direct children need scanning here, not a full subtree walk.
    for stmt in init_node.body:
        if not isinstance(stmt, ast.AnnAssign):
            continue
        target = stmt.target
        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == _SELF
        ):
            continue
        attr_location = _location(source, target)
        attr_type = resolve_annotation(
            stmt.annotation,
            attr_location,
            source,
            diagnostics,
            what=f"attribute '{target.attr}' of '{class_name}'",
            known_classes=known_classes,
        )
        if attr_type is None:
            ok = False
            continue
        if target.attr in inherited:
            if attr_type != inherited[target.attr].type:
                diagnostics.error(
                    codes.DUPLICATE_DEFINITION,
                    f"attribute '{target.attr}' is already defined on an ancestor of "
                    f"'{class_name}' with type '{inherited[target.attr].type}'",
                    attr_location,
                    help_text="giving it a different type here would need two same-named C++ "
                    "struct fields, which isn't supported",
                )
                ok = False
            # Same name, same type as the inherited attribute: this is a
            # plain reassignment of the field the base class's '__init__'
            # already initialized (e.g. super().__init__() sets a default,
            # then this constructor overwrites it with a real value) --
            # not a new field, so nothing is added to this class's own
            # 'attributes' below.
            continue
        if target.attr in attributes:
            diagnostics.error(
                codes.DUPLICATE_DEFINITION,
                f"attribute '{target.attr}' is already declared on '{class_name}'",
                attr_location,
                help_text=f"the previous declaration is at {attributes[target.attr].location}",
            )
            ok = False
            continue
        attributes[target.attr] = AttributeSymbol(
            name=target.attr, type=attr_type, location=attr_location
        )
    return attributes if ok else None


def _collect_method(
    node: ast.FunctionDef,
    class_name: str,
    source: SourceFile,
    diagnostics: DiagnosticEngine,
    *,
    known_classes: frozenset[str],
) -> MethodSymbol | None:
    location = _location(source, node)
    parameters = _collect_parameters(
        node.args,
        source,
        diagnostics,
        known_classes=known_classes,
        skip_self=True,
        owner=f"{class_name}.{node.name}",
    )
    return_type = resolve_annotation(
        node.returns,
        location,
        source,
        diagnostics,
        what=f"method '{class_name}.{node.name}'s return value",
        known_classes=known_classes,
    )
    if parameters is None or return_type is None:
        return None
    return MethodSymbol(
        name=node.name, parameters=tuple(parameters), return_type=return_type, location=location
    )
