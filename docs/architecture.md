# Architecture

This document explains how py2cpp is built and why it's shaped the way it
is. It assumes you've read the [README](../README.md); if you're about to
add a new Python feature, read
[`adding-python-feature.md`](adding-python-feature.md) first — it walks
through the same pipeline described here, but as a hands-on checklist.

## Guiding priorities

Every design decision in this codebase is made against one ordered list of
priorities:

1. semantic correctness
2. explicit failure instead of incorrect code generation
3. clear diagnostics
4. maintainable compiler architecture
5. testability
6. portability
7. readable generated C++
8. contributor friendliness
9. performance
10. feature count

The rule that overrides everything else: **when Python semantics can't be
reproduced safely in C++, py2cpp does not guess.** It rejects the program
with a precise diagnostic rather than silently emitting C++ that might
behave differently from the Python source. You'll see this rule show up
concretely throughout the pipeline below — as structural restrictions in
the frontend, as type-checking failures in the IR builder, and as an
internal-error checkpoint just before code generation.

## The pipeline

py2cpp compiles a source file in five stages, each with a narrow, single
responsibility. Data flows one direction only — nothing downstream ever
reaches back upstream to re-derive something it should already have been
given.

```
 .py file
    |
    v
+------------------+   stdlib ast.parse()
|  frontend/        |   - loader.py    read the file
|                    |   - parser.py    Python source -> ast.AST
|                    |   - subset.py    "is this syntax shape allowed?"
|                    |   - literals.py  literal-extraction helpers
+------------------+
    |  ast.AST (subset-validated)
    v
+------------------+
|  semantic/         |   - symbols.py     symbol dataclasses
|                    |   - collect.py     ast.AST -> SymbolTable
|                    |   - annotations.py type-annotation -> Type
|                    |   - exceptions.py  curated exception hierarchy
+------------------+
    |  SymbolTable (every function/class/attribute signature, pre-resolved)
    v
+------------------+
|  ir/lower.py       |   ast.AST + SymbolTable -> IR
|  (name resolution + type checking + IR construction, combined)
+------------------+
    |  IRModule (typed, validated tree)
    v
+------------------+
|  ir/validate.py    |   final invariant checkpoint (py2cpp bug if it fires,
|                    |   never a user error -- see "Two kinds of failure")
+------------------+
    |  IRModule (guaranteed well-formed)
    v
+------------------+
|  backend/          |   - types_cpp.py       Type -> C++ spelling
|  emit_cpp.py        |   - mangling.py        C++ keyword collisions
|  (pure, mechanical  |   - string_literals.py byte-safe string escaping
|   IR -> text)       |   - writer.py          indent-tracking emitter
+------------------+
    |
    v
 .cpp file (+ pyrt/ runtime headers, if --emit-runtime)
```

### Frontend (`src/py2cpp/frontend/`)

The frontend never writes its own parser — `loader.py` reads the file and
`parser.py` is a thin wrapper around stdlib `ast.parse()`, turning a
`SyntaxError` into a `Diagnostic` instead of propagating the exception.

`subset.py` is where "is this syntax shape allowed *this milestone*?" gets
decided, structurally, on the raw `ast.AST` — before any name resolution
or type checking happens. Most of the restrictions listed in the
[README's "Restrictions" section](../README.md) are enforced here: e.g.
`return` may only be a function's final top-level statement, chained
comparisons (`a < b < c`) are rejected outright, `self` may only ever be
the receiver of `.attr`/`.method(...)`. Rejecting a shape here, before it
ever reaches lowering, keeps the rest of the pipeline simpler: everything
downstream can assume the shapes it's willing to handle are the only
shapes it will ever see.

### Semantic analysis (`src/py2cpp/semantic/`)

`collect.py` walks the module once and builds a `SymbolTable`: every
function, class, method, and attribute signature, fully resolved, before
any function body gets lowered. This is what lets a function call another
function defined later in the file, or a class hold an attribute typed as
itself (`self.next: Node`) — the *name* `Node` is known from the first
collection pass, even though its class body isn't lowered until later.

`annotations.py` turns a Python type annotation (`int`, `list[str]`,
`dict[str, int]`, a known class name, ...) into a `Type` from
`types/model.py`. `exceptions.py` holds the curated, fixed
`EXCEPTION_HIERARCHY` — unlike classes and functions, exception types
aren't collected from source, because user code can't define new exception
types yet (see "Two open design gaps" below).

### Types (`src/py2cpp/types/`)

`types/model.py` defines the `Type` hierarchy: `IntType`, `BoolType`,
`StringType`, `ListType`/`DictType`/`SetType`/`TupleType` (parameterized by
their element types), `ClassType`, `ExceptionType`. `types/join.py` is
deliberately **hierarchy-agnostic** — it only knows the primitive
bool-widens-to-int coercion rule and container-with-identical-shape
joining. Class subtyping (is `Dog` assignable where `Animal` is expected?)
lives one layer up, in `ir/lower.py`'s `_assignable()`/`_is_subclass()`,
which *compose* the pure type-system rules from `join.py` with the class
hierarchy from `SymbolTable`. Keeping these separate means the type system
itself never needs to know classes exist.

### IR (`src/py2cpp/ir/`)

`ir/nodes.py` defines a typed, project-specific IR — a set of frozen
dataclasses for every expression and statement shape py2cpp can emit (see
`nodes.py` itself for the exhaustive, current list; it changes every
milestone). This IR is the hard boundary the project's absolute rules
protect: **the backend never sees `ast.AST`, and the frontend/semantic
layers never produce C++ text.** Anything that needs to reason about
Python semantics happens once, in `lower.py`, and everything downstream of
the IR is a mechanical, un-opinionated translation.

`ir/lower.py` is intentionally the largest module in the project. It does
three things at once, statement by statement and expression by expression:
name resolution (is this identifier defined? which symbol does it refer
to?), type checking (are these operand types compatible? does this
assignment widen safely?), and IR construction (build the typed node that
represents this). These three concerns were kept in one pass rather than
split into three separate passes over the tree, because in this language
subset they're inseparable in practice — you can't decide whether `a + b`
type-checks without already knowing what `a` and `b` resolve to, and by
the time you know that, you already have everything you need to build the
IR node. Splitting them into more "textbook" separate compiler passes
would mean re-deriving the same information three times for no benefit
this project's scope actually needs.

`ir/validate.py` runs once, after lowering, as a final invariant
checkpoint. See "Two kinds of failure" below for why it exists as a
separate step from `lower.py`'s own checks.

### Backend (`src/py2cpp/backend/`)

`emit_cpp.py` is a pure, mechanical translator: given a well-formed
`IRModule`, it writes C++17 text. It never re-derives semantics — if a
question like "is this method virtual?" or "is this variable's type
`shared_ptr<Foo>` or a plain scalar?" needs answering, that answer was
already computed and stored on the IR node by `lower.py`; the backend just
formats it. `types_cpp.py` maps each `Type` to its C++ spelling (including
the reference-semantics choice for classes and containers — see
"Reference semantics" below). `mangling.py` escapes identifiers that
collide with C++ keywords. `string_literals.py` escapes UTF-8 string
literals byte-by-byte so they survive unmodified across GCC, Clang, and
MSVC regardless of the compiler's source/execution charset assumptions.
`writer.py` is a small indent-tracking line emitter used by everything
else in the package.

## Two kinds of failure

py2cpp distinguishes sharply between two failure categories, and they are
never allowed to look the same to a user:

- **A diagnostic** (`P2C####`, printed as
  `file.py:line:col: error[P2C####]: message`, sometimes with a `help:`
  line) means *the input program uses a construct py2cpp doesn't support,
  or doesn't support in a way that's safe to translate.* This is the
  expected, designed-for outcome for any program outside the supported
  subset. See `codes.py` for the full registry (`P2C1xxx` = frontend/
  subset shape, `P2C2xxx` = semantic/name resolution, `P2C3xxx` = type
  checking).

- **An `InternalCompilerError`** (`P2C9001`) means *py2cpp itself has a
  bug* — an invariant that `lower.py` believed it had already established
  turned out not to hold by the time `ir/validate.py` double-checked it
  just before code generation. This should never fire on any program that
  got past the frontend and semantic stages; if it does, it's a py2cpp
  issue to file, not a signal that the input program is invalid.

Keeping `ir/validate.py` as a distinct final pass — rather than trusting
`lower.py`'s own bookkeeping — means a mistake in the (large, fast-moving)
lowering logic is caught before it can reach the backend and silently
produce C++ that doesn't do what the IR claims it does.

## Reference semantics for classes and containers

Python's object model is reference-based: `a = b` for two class instances
or two lists makes `a` and `b` the same object — mutating through one is
visible through the other. C++ value types don't behave that way by
default, so py2cpp deliberately opts every class instance and every
container into aliasing semantics rather than trying to infer, case by
case, when a copy would be observably different from a Python program's
behavior:

- Every class-typed variable, parameter, attribute, and return value is
  `std::shared_ptr<ClassName>`; `Foo(args)` compiles to
  `std::make_shared<Foo>(args)`.
- `pyrt::List`/`pyrt::Dict`/`pyrt::Set` each wrap a `std::shared_ptr` to
  their backing storage; assignment copies the (cheap) `shared_ptr`, not
  the contents.
- Scalars (`int`/`bool`/`str`) and `tuple` (mapped to a genuine
  `std::tuple<...>`) stay true value types, matching Python's own
  value-semantics for immutable types.

This is also what makes closed-world virtual dispatch possible (a
base-typed variable can hold a derived instance, which is the whole point
of dispatching on it) — see the class-hierarchy note below.

## Closed-world class hierarchy analysis

py2cpp compiles a whole program as a single compilation unit and commits
to *closed-world* analysis of the class hierarchy: before any class body
is lowered, `ir/lower.py::_compute_virtual_methods()` walks every class's
method names up its base chain, once, over the entire `SymbolTable`. A
method is emitted `virtual` **iff it's actually overridden somewhere in
the compiled program** — computed, never left to a user-supplied
`virtual` keyword, so there's no risk of a silent mismatch between what's
declared virtual and what's actually overridden. Non-overridden methods
stay non-virtual, which keeps generated C++ both faster and easier to
read. The cost of this is a real, documented v1 limitation: py2cpp cannot
support separate compilation units that might add further overrides of a
class it doesn't know about.

## Two open design gaps

Two things flagged during class support (M5) and exception support (M6)
remain open, deliberately, rather than worked around:

- **No `Optional`/`None` for class-typed values.** A genuinely
  null-terminated or cyclic structure (e.g. a linked list's tail) can't be
  built yet, because every class-typed field needs a real instance.
- **User-defined exception subclasses aren't supported**
  (`class ConfigError(ValueError): ...`) — the class-hierarchy system
  (M5) and the exception-hierarchy system (M6) don't interact yet;
  exceptions are matched against a fixed, curated hierarchy, not
  `SymbolTable`'s class hierarchy.

Both are real gaps against full Python, not oversights, and both are
flagged in the modules most relevant to them (`ir/lower.py`,
`semantic/exceptions.py`).

## Diagnostics

`diagnostics.py` defines `SourceLocation`, `Severity`, `Diagnostic`, and
`DiagnosticEngine` — the shared vocabulary every stage of the pipeline
uses to report a problem. A `Diagnostic` always carries a precise source
location and a `P2C####` code from `codes.py`; an optional `help:` line
gives a next step when one is genuinely actionable (not for every
diagnostic — a generic "try something else" isn't help). `compiler.py`'s
`compile_source()` is the single public entry point that runs the whole
pipeline and returns a `CompilationResult` carrying either emitted C++ or
a `DiagnosticEngine` full of everything that went wrong; the CLI
(`cli.py`) is a thin argument-parsing layer over that same function.
