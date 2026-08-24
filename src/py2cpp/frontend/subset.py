"""Structural subset validation.

This pass answers only "is this syntax shape permitted by the v1 subset",
independent of what any name resolves to or what type anything has. Name
resolution and type checking happen later (see semantic/collect.py and
ir/lower.py) and can assume the tree already satisfies these shape rules.

Notable scoping restrictions for this milestone (documented rather than
silently applied):

- 'return' may only appear as the final statement of a function's own
  top-level body -- never nested inside if/while/for, and never more than
  once. Early/multiple return points are a future milestone; this keeps
  every function body a straight sequence ending in one return, which
  keeps definite-assignment and codegen simple while still allowing rich
  conditional logic to compute the value that gets returned.
- chained comparisons ('a < b < c') are rejected: naively translating them
  to C++ would silently compute '(a < b) < c' instead of Python's
  '(a < b) and (b < c)', which is exactly the kind of silent behavioral
  divergence this project refuses to produce.
- 'and'/'or'/'not' require bool operands (i.e. comparison results),
  not Python's general "return one of the operands" semantics -- that
  would need either double-evaluating the left operand or a place to
  stash a temporary, neither of which this milestone's expression-only
  IR has.
- a 'for' loop's 'step' argument, when given, must be a compile-time
  integer literal, so the loop's direction (< vs >) can be chosen
  statically instead of needing a runtime branch.
- list/dict/set literals must be non-empty: with no elements, there is
  nothing to infer an element/key/value type from, and this milestone
  does not thread an expected-type hint in from an annotated target the
  way e.g. a plain int literal never needs one.
- comprehensions support exactly one 'for' clause and at most one 'if'
  clause -- multi-clause/nested comprehensions are a future milestone.
- container mutation ('.append(...)', 'd[k] = v'), 'in'/'not in', tuple
  unpacking in a 'for' target, and iterating a tuple are all deferred;
  containers this milestone are built via literals/comprehensions and
  read via indexing/iteration only.
- a class must define its own '__init__' (constructors are not inherited);
  if it has a base class, '__init__''s first statement must be a
  'super().__init__(...)' call -- Python doesn't chain base constructors
  implicitly, so py2cpp doesn't invent that either.
- an attribute ('self.x: T = value') may only be declared as a direct,
  unconditional top-level statement of '__init__' -- never nested inside
  an if/while/for there. This guarantees every declared attribute is
  unconditionally initialized whenever '__init__' runs, matching a C++
  struct member's "always exists" guarantee; a conditionally-declared
  attribute would leave the member uninitialized on some paths.
- only single inheritance, no class variables/static/class methods, no
  properties, no operator-overload dunders, and no dunder methods other
  than '__init__'.
- 'self' may only be used as the receiver of an attribute access or
  method call ('self.x', 'self.method(...)') -- never returned, stored,
  passed as an argument, or otherwise used as a value. Every other
  class-typed value is backed by a real std::shared_ptr and can be used
  freely, but 'self' inside a method is C++'s raw 'this'; recovering a
  shared_ptr to it needs std::enable_shared_from_this, which cannot be
  called from inside the object's own constructor -- since '__init__'
  always maps to a constructor, that would make 'self' usable as a value
  in ordinary methods but not '__init__', an asymmetry not worth the
  complexity for what it would unlock, so this milestone disallows it
  uniformly instead of guessing case by case.
"""

from __future__ import annotations

import ast
from typing import TypeGuard

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.literals import extract_int_literal
from py2cpp.frontend.loader import SourceFile

_ALLOWED_BINOPS: tuple[type[ast.operator], ...] = (ast.Add, ast.Sub, ast.Mult)
_ALLOWED_COMPARE_OPS: tuple[type[ast.cmpop], ...] = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def validate_subset(tree: ast.Module, source: SourceFile, diagnostics: DiagnosticEngine) -> None:
    _SubsetValidator(source, diagnostics).visit(tree)


class _SubsetValidator(ast.NodeVisitor):
    def __init__(self, source: SourceFile, diagnostics: DiagnosticEngine) -> None:
        self._source = source
        self._diagnostics = diagnostics

    def _location(self, node: ast.AST) -> SourceLocation:
        return SourceLocation(
            filename=self._source.path,
            line=getattr(node, "lineno", 1),
            column=getattr(node, "col_offset", 0) + 1,
        )

    def _reject(self, node: ast.AST, message: str, help_text: str | None = None) -> None:
        self._diagnostics.error(codes.UNSUPPORTED_SYNTAX, message, self._location(node), help_text)

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef):
                self._validate_function(stmt)
            elif isinstance(stmt, ast.ClassDef):
                self._validate_class(stmt)
            else:
                self._validate_stmt(stmt, allow_return=False)

    def _validate_function(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            self._reject(node.decorator_list[0], "decorators are not supported")

        self._validate_plain_params(node.args, node)

        if not node.body:
            self._reject(node, "function body must not be empty")
            return
        self._validate_block(node.body, allow_return=True)

    def _validate_plain_params(self, args: ast.arguments, node: ast.AST) -> None:
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs or args.defaults:
            self._reject(
                node,
                "only plain positional parameters are supported "
                "(no *args, **kwargs, defaults, or keyword-only parameters)",
            )

    def _validate_class(self, node: ast.ClassDef) -> None:
        if node.decorator_list:
            self._reject(node.decorator_list[0], "decorators are not supported")
        if node.keywords:
            self._reject(node, "class keyword arguments (e.g. metaclass=) are not supported")
        if len(node.bases) > 1:
            self._reject(node, "multiple inheritance is not supported in this milestone")
        has_base = len(node.bases) == 1
        if has_base and not isinstance(node.bases[0], ast.Name):
            self._reject(node.bases[0], "a base class must be a plain class name")
            has_base = False

        init_node: ast.FunctionDef | None = None
        for stmt in node.body:
            if not isinstance(stmt, ast.FunctionDef):
                self._reject(
                    stmt,
                    "only method definitions (and '__init__') are supported in a class body "
                    "in this milestone",
                    help_text="no class variables, nested classes, or other statements yet",
                )
                continue
            if stmt.name == "__init__":
                if init_node is not None:
                    self._reject(stmt, "a class may only define one '__init__'")
                    continue
                init_node = stmt
            elif stmt.name.startswith("__") and stmt.name.endswith("__"):
                self._reject(
                    stmt,
                    f"dunder method '{stmt.name}' is not supported in this milestone "
                    "('__init__' is the only one)",
                )
            else:
                self._validate_method(stmt)

        if init_node is None:
            self._reject(node, f"class '{node.name}' must define an '__init__' method")
            return
        self._validate_init(init_node, has_base=has_base)

    def _validate_self_param(self, node: ast.FunctionDef) -> None:
        args = node.args
        self._validate_plain_params(args, node)
        if not args.args or args.args[0].arg != "self":
            self._reject(node, "a method's first parameter must be named 'self'")
            return
        if args.args[0].annotation is not None:
            self._reject(args.args[0], "'self' must not have a type annotation")

    def _validate_method(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            self._reject(node.decorator_list[0], "decorators are not supported")
        self._validate_self_param(node)
        if not node.body:
            self._reject(node, "method body must not be empty")
            return
        self._validate_block(node.body, allow_return=True)

    def _is_super_init_call(self, node: ast.Call) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "__init__"
            and self._is_super_call(node.func.value)
        )

    def _validate_init(self, node: ast.FunctionDef, *, has_base: bool) -> None:
        self._validate_self_param(node)
        body = node.body

        start = 0
        if has_base:
            first = body[0] if body else None
            is_super_init = (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Call)
                and self._is_super_init_call(first.value)
            )
            if not is_super_init:
                self._reject(
                    node,
                    "a subclass's '__init__' must call 'super().__init__(...)' as its first "
                    "statement",
                    help_text="py2cpp does not chain base-class constructors implicitly",
                )
            else:
                assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
                self._validate_call(first.value)
                start = 1

        for stmt in body[start:]:
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and self._is_super_init_call(stmt.value)
            ):
                self._reject(
                    stmt,
                    "'super().__init__(...)' may only appear as '__init__''s first statement",
                )
                continue
            self._validate_stmt(stmt, allow_return=False, at_init_top_level=True)

        for descendant in ast.walk(node):
            if isinstance(descendant, ast.Return):
                self._reject(descendant, "'__init__' must not contain a 'return' statement")

    def _validate_block(self, stmts: list[ast.stmt], *, allow_return: bool) -> None:
        last_index = len(stmts) - 1
        for i, stmt in enumerate(stmts):
            self._validate_stmt(stmt, allow_return=allow_return and i == last_index)

    def _validate_stmt(
        self, stmt: ast.stmt, *, allow_return: bool, at_init_top_level: bool = False
    ) -> None:
        if isinstance(stmt, ast.Return):
            if not allow_return:
                self._reject(
                    stmt,
                    "'return' may only appear as the final statement of a function body "
                    "in this milestone",
                    help_text="early/multiple return points arrive in a later milestone",
                )
                return
            if stmt.value is None:
                self._reject(stmt, "'return' must return a value")
                return
            self._validate_expr(stmt.value)
        elif isinstance(stmt, ast.Assign):
            self._validate_assign_target(stmt.targets, stmt)
            self._validate_expr(stmt.value)
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Attribute):
                if not (
                    at_init_top_level
                    and isinstance(stmt.target.value, ast.Name)
                    and stmt.target.value.id == "self"
                ):
                    self._reject(
                        stmt,
                        "an attribute may only be declared ('self.x: T = value') as a direct, "
                        "unconditional top-level statement of '__init__'",
                    )
                    return
            elif not isinstance(stmt.target, ast.Name):
                self._reject(
                    stmt,
                    "only simple 'name: type = value' assignment is supported in this milestone",
                )
                return
            if stmt.value is None:
                self._reject(stmt, "annotated assignment must have a value in this milestone")
                return
            self._validate_expr(stmt.value)
        elif isinstance(stmt, ast.If):
            self._validate_expr(stmt.test)
            self._validate_block(stmt.body, allow_return=False)
            self._validate_block(stmt.orelse, allow_return=False)
        elif isinstance(stmt, ast.While):
            if stmt.orelse:
                self._reject(stmt, "'while ... else' is not supported")
            self._validate_expr(stmt.test)
            self._validate_block(stmt.body, allow_return=False)
        elif isinstance(stmt, ast.For):
            self._validate_for(stmt)
            self._validate_block(stmt.body, allow_return=False)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            self._validate_call(stmt.value)
        elif isinstance(stmt, ast.Pass):
            pass
        else:
            self._reject(
                stmt,
                f"statement of kind '{type(stmt).__name__}' is not supported in this milestone",
            )

    def _is_bare_self(self, node: ast.expr) -> bool:
        return isinstance(node, ast.Name) and node.id == "self"

    def _validate_receiver(self, node: ast.expr) -> None:
        """Validates the object expression of an attribute/method access
        ('obj' in 'obj.attr' or 'obj.method(...)'). 'self' is always a
        valid receiver without needing further validation; anything else
        is validated as an ordinary expression (which itself rejects a
        bare 'self' anywhere other than exactly this position).
        """

        if not self._is_bare_self(node):
            self._validate_expr(node)

    def _validate_assign_target(self, targets: list[ast.expr], stmt: ast.stmt) -> None:
        if len(targets) != 1:
            self._reject(stmt, "only a single assignment target is supported in this milestone")
            return
        target = targets[0]
        if isinstance(target, ast.Name):
            return
        if isinstance(target, ast.Attribute):
            self._validate_receiver(target.value)
            return
        self._reject(
            stmt,
            "only 'name = value' or 'obj.attr = value' assignment is supported in this milestone",
        )

    def _validate_for(self, node: ast.For) -> None:
        if node.orelse:
            self._reject(node, "'for ... else' is not supported")
        if not isinstance(node.target, ast.Name):
            self._reject(node.target, "the loop variable must be a plain name")
        if self._is_range_call(node.iter):
            self._validate_range_call(node.iter)
            return
        # Not a 'range(...)' call: validated as a general container
        # expression here; whether it's actually an iterable type (and,
        # for a dict, that iteration yields keys) is a semantic question
        # resolved later, in ir/lower.py.
        self._validate_expr(node.iter)

    def _is_range_call(self, node: ast.expr) -> TypeGuard[ast.Call]:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "range"
        )

    def _validate_range_call(self, range_call: ast.Call) -> None:
        if range_call.keywords or not (1 <= len(range_call.args) <= 3):
            self._reject(range_call, "'range' takes 1 to 3 positional arguments")
            return
        for i, arg in enumerate(range_call.args):
            self._validate_expr(arg)
            if i == 2 and extract_int_literal(arg) is None:
                self._reject(
                    arg,
                    "'range' step must be a literal integer constant in this milestone",
                    help_text="a runtime-computed step arrives in a later milestone",
                )

    def _validate_comprehension(self, node: ast.ListComp) -> None:
        if len(node.generators) != 1:
            self._reject(
                node,
                "comprehensions with more than one 'for' clause are not supported "
                "in this milestone",
            )
            return
        generator = node.generators[0]
        if generator.is_async:
            self._reject(node, "async comprehensions are not supported")
            return
        if not isinstance(generator.target, ast.Name):
            self._reject(generator.target, "the comprehension variable must be a plain name")
        if self._is_range_call(generator.iter):
            self._validate_range_call(generator.iter)
        else:
            self._validate_expr(generator.iter)
        if len(generator.ifs) > 1:
            self._reject(
                node,
                "comprehensions with more than one 'if' clause are not supported "
                "in this milestone",
            )
        for condition in generator.ifs:
            self._validate_expr(condition)
        self._validate_expr(node.elt)

    def _validate_fstring(self, node: ast.JoinedStr) -> None:
        for value in node.values:
            if isinstance(value, ast.Constant):
                continue
            if isinstance(value, ast.FormattedValue):
                if value.conversion != -1:
                    self._reject(
                        value,
                        "f-string conversions ('!r', '!s', '!a') are not supported "
                        "in this milestone",
                    )
                if value.format_spec is not None:
                    self._reject(
                        value.format_spec,
                        "f-string format specs are not supported in this milestone",
                    )
                self._validate_expr(value.value)
            else:
                self._reject(value, "unsupported f-string component")  # pragma: no cover

    def _is_super_call(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "super"
            and not node.args
            and not node.keywords
        )

    def _validate_call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id == "super":
                self._reject(
                    node, "'super()' may only be used as 'super().__init__(...)' in this milestone"
                )
                return
        elif isinstance(node.func, ast.Attribute):
            if self._is_super_call(node.func.value):
                if node.func.attr != "__init__":
                    self._reject(
                        node,
                        "'super()' may only be used as 'super().__init__(...)' in this milestone",
                    )
                    return
            else:
                self._validate_receiver(node.func.value)
        else:
            self._reject(
                node, "only calls to a plain function name or 'obj.method(...)' are supported"
            )
            return
        if node.keywords:
            self._reject(node, "keyword arguments are not supported")
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                self._reject(arg, "*args-style call arguments are not supported")
            else:
                self._validate_expr(arg)

    def _validate_expr(self, node: ast.expr) -> None:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, str)):
                self._reject(
                    node, "only integer and string literals are supported in this milestone"
                )
        elif isinstance(node, ast.JoinedStr):
            self._validate_fstring(node)
        elif isinstance(node, (ast.List, ast.Set)):
            if not node.elts:
                self._reject(
                    node,
                    "an empty list/set literal is not supported in this milestone "
                    "(its element type can't be inferred)",
                )
            for element in node.elts:
                self._validate_expr(element)
        elif isinstance(node, ast.Tuple):
            for element in node.elts:
                self._validate_expr(element)
        elif isinstance(node, ast.Dict):
            if not node.keys:
                self._reject(
                    node,
                    "an empty dict literal is not supported in this milestone "
                    "(its key/value types can't be inferred)",
                )
            for key, value in zip(node.keys, node.values, strict=True):
                if key is None:
                    self._reject(value, "'**' unpacking in a dict literal is not supported")
                    continue
                self._validate_expr(key)
                self._validate_expr(value)
        elif isinstance(node, ast.Subscript):
            self._validate_expr(node.value)
            self._validate_expr(node.slice)
        elif isinstance(node, ast.Attribute):
            self._validate_receiver(node.value)
        elif isinstance(node, ast.ListComp):
            self._validate_comprehension(node)
        elif isinstance(node, ast.Name):
            if node.id == "self":
                self._reject(
                    node,
                    "'self' can only be used as 'self.attr' or 'self.method(...)' in this "
                    "milestone",
                    help_text="returning, storing, or passing 'self' as a value isn't supported",
                )
        elif isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_BINOPS):
                self._reject(
                    node, f"operator '{type(node.op).__name__}' is not supported in this milestone"
                )
            self._validate_expr(node.left)
            self._validate_expr(node.right)
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                self._reject(
                    node,
                    "chained comparisons (e.g. 'a < b < c') are not supported in this milestone",
                    help_text="write it as 'a < b and b < c'",
                )
                return
            if not isinstance(node.ops[0], _ALLOWED_COMPARE_OPS):
                self._reject(
                    node,
                    f"comparison '{type(node.ops[0]).__name__}' is not supported in this milestone",
                )
            self._validate_expr(node.left)
            self._validate_expr(node.comparators[0])
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                self._validate_expr(value)
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                if extract_int_literal(node) is None:
                    self._reject(
                        node,
                        "unary '-' is only supported on integer literals in this milestone",
                        help_text="negating an arbitrary expression arrives in a later milestone",
                    )
            elif isinstance(node.op, ast.Not):
                self._validate_expr(node.operand)
            else:
                self._reject(
                    node,
                    f"unary operator '{type(node.op).__name__}' is not supported in this milestone",
                )
        elif isinstance(node, ast.Call):
            self._validate_call(node)
        else:
            self._reject(
                node,
                f"expression of kind '{type(node).__name__}' is not supported in this milestone",
            )
