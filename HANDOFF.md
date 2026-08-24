# py2cpp — Project Handoff

This document exists so a **new Claude Code chat session** can pick up this
project with full context, without re-deriving decisions already made. Paste
this file's content (or point Claude at it) at the start of a new session.

Repository: **https://github.com/edpl22/py2cpp** (public)
Local path: `c:\Users\Palos\Desktop\transpilador`
License: MIT

---

## 1. What this project is

`py2cpp` is a transpiler, **written in Python**, that translates a
well-defined, explicitly-scoped subset of **Python 3.10+** into readable,
compilable **C++17**. It is not trying to become a general-purpose Python
implementation — see §5 (non-goals) below.

Core engineering priorities, in order (this ordering drives every design
call in the project):

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

**The rule that overrides everything else:** when Python semantics can't be
reproduced safely, py2cpp does not guess. It rejects the program with a
precise diagnostic (`file.py:line:col: error[P2C####]: message` + optional
`help:` line) rather than silently emitting C++ that might behave
differently from the Python source.

---

## 2. Absolute development rules (do not relax these)

- **The compiler is implemented in Python.** C++ is only ever generated
  output, plus the small header-only runtime `pyrt` (`include/pyrt/`).
- **All dev work happens inside `.venv/`.**
- **Dependencies are installed only via `requirements.txt`** — never
  `pip install <package>` individually. Every new dependency needs a
  justification added as a comment in `requirements.txt`.
- **No custom Python parser** — the frontend uses stdlib `ast`.
- **Never emit C++ directly from `ast.AST`.** There is a typed, project-
  specific IR (`src/py2cpp/ir/nodes.py`) between the Python AST and the C++
  emitter. The backend (`src/py2cpp/backend/`) is a pure, mechanical
  translator — it never re-derives semantics, only formats.
- **No `eval`/`exec`** anywhere in the compiler (only permitted inside
  golden tests, to run the *original* Python program as the correctness
  oracle).
- **No speculative overengineering.** Types, IR nodes, and runtime (`pyrt`)
  headers are added only when the milestone that needs them lands. Do not
  build ahead.
- **Milestones are executed one at a time.** After finishing a milestone:
  run the full acceptance suite for real (never claim a check passed
  without running it; report `NOT RUN` honestly for anything that couldn't
  be verified — e.g. a missing compiler), report status, propose a
  Conventional Commit message, and **STOP** — wait for explicit
  instruction before starting the next milestone.
- **Only commit/push when explicitly asked.** Never force-push, never
  `git reset --hard` without being asked, always inspect `git status`
  before anything destructive.
- Public, project-wide semantic decisions (see §6) get discussed with the
  user *before* implementation — options/pros/cons/recommendation, then
  wait for a decision. Small, reversible, milestone-scoped restrictions
  (e.g. "range's step must be a compile-time literal this milestone") are
  fine to decide unilaterally as long as they're clearly flagged in the
  completion report, not silently applied.

---

## 3. Repository layout (current, real — not aspirational)

```
py2cpp/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                  # ubuntu/macos/windows × py3.10-3.13, ruff+mypy+pytest; installs clang (Linux)/sets up MSVC (Windows) so the golden tests' g++/clang++/cl parametrization isn't all-skip
│   │   └── release.yml             # build+twine-check on every push/PR; publish to PyPI via Trusted Publishing (OIDC) on GitHub Release "published"
│   └── ISSUE_TEMPLATE/             # bug_report.yml, feature_request.yml, config.yml
├── docs/
│   ├── architecture.md             # pipeline walkthrough: frontend -> semantic -> types -> ir -> backend, Two kinds of failure, reference semantics, closed-world dispatch
│   └── adding-python-feature.md    # step-by-step guide for contributing a new language feature, using a hypothetical len() as the running example
├── examples/                       # classify.py (existing) + strings.py, containers.py, classes.py, exceptions.py (M7) — each compiled+diffed against CPython before being added, see §4
├── CHANGELOG.md                    # Keep a Changelog format; Unreleased + 0.1.0 sections
├── CODE_OF_CONDUCT.md              # Contributor Covenant v2.1
├── include/pyrt/                  # header-only C++ runtime
│   ├── pyrt.hpp                   # umbrella header (sibling-relative includes! order matters, see its own comment)
│   ├── operators.hpp              # overflow-checked add/sub/mul/floordiv for int64
│   ├── exceptions.hpp             # pyrt::PyException hierarchy (Decision E) — ValueError, TypeError, LookupError->{IndexError,KeyError}, ArithmeticError->{ZeroDivisionError,OverflowError}
│   ├── string.hpp                 # pyrt::Str — UTF-8 bytes, whole-string ops only (no indexing yet)
│   ├── repr.hpp                   # pyrt::detail::write_repr — shared print/repr dispatch (bool, Str, std::tuple)
│   ├── print.hpp                  # variadic print; delegates to write_repr except a bare Str (unquoted)
│   ├── list.hpp                   # pyrt::List<T> — shared_ptr<deque<T>>-backed, negative indexing
│   ├── dict.hpp                   # pyrt::Dict<K,V> — shared_ptr<vector<pair<K,V>>>-backed, insertion-ordered
│   └── set.hpp                    # pyrt::Set<T> — shared_ptr<deque<T>>-backed, insertion-ordered, dedups on construction
├── src/py2cpp/
│   ├── __init__.py                 # __version__ lives here (single source of truth)
│   ├── __main__.py
│   ├── cli.py                      # argparse; --version works, full flag surface declared
│   ├── compiler.py                 # CompilerOptions/CompilationResult/compile_source() — the public API
│   ├── diagnostics.py              # SourceLocation, Severity, Diagnostic, DiagnosticEngine
│   ├── codes.py                    # P2C#### diagnostic code registry (see §7)
│   ├── frontend/
│   │   ├── loader.py                # SourceFile, load_source(), SourceLoadError
│   │   ├── parser.py                # ast.parse() wrapper -> Diagnostic on SyntaxError
│   │   ├── subset.py                # structural "is this syntax shape allowed" validator
│   │   └── literals.py              # extract_int_literal(): handles '-2' == UnaryOp(USub, Constant(2))
│   ├── semantic/
│   │   ├── symbols.py               # ParameterSymbol, FunctionSymbol, ClassSymbol, AttributeSymbol, MethodSymbol, SymbolTable
│   │   ├── collect.py               # builds SymbolTable from FunctionDefs/ClassDefs
│   │   ├── annotations.py           # resolve_annotation(): scalars + list[T]/dict[K,V]/set[T]/tuple[T,...] subscripts + known class names
│   │   └── exceptions.py            # EXCEPTION_HIERARCHY: py2cpp's fixed, curated exception registry (see §6/§7, Decision E)
│   ├── types/
│   │   ├── model.py                  # Type, IntType, BoolType, StringType, ListType, DictType, SetType, TupleType, ClassType, ExceptionType
│   │   └── join.py                   # join(), is_assignable() — bool widens to int, one-way; containers join only with an identical container type; hierarchy-agnostic (class/exception subtyping lives in ir/lower.py instead)
│   ├── ir/
│   │   ├── nodes.py                  # typed IR dataclasses (see §7)
│   │   ├── lower.py                  # THE big one: combined name-resolution + type-check + IR build
│   │   └── validate.py               # final invariant checkpoint; raises InternalCompilerError (py2cpp bug, not user error)
│   └── backend/
│       ├── writer.py                 # CodeWriter: indent-tracking line emitter
│       ├── types_cpp.py              # Type -> C++ spelling
│       ├── mangling.py               # escape_identifier(): C++ keyword collision guard
│       ├── string_literals.py        # cpp_string_literal(): UTF-8-byte-safe, portable C++ string literal escaping
│       └── emit_cpp.py               # IR -> C++17 text
├── tests/
│   ├── unit/                         # one dir per src/py2cpp subpackage
│   ├── integration/                  # golden tests, negative-case runner, overflow test, emit-runtime test
│   ├── cases/valid/ , cases/invalid/ # .py fixtures (+ .json sidecar with expected diagnostic code for invalid/)
│   └── support/                      # toolchain.py (compiler discovery via shutil.which), pipeline.py (CPython/py2cpp runners)
├── pyproject.toml                    # hatchling, ruff/mypy/pytest/coverage config
├── requirements.txt                  # -e ., pytest, pytest-cov, ruff, mypy, pre-commit — nothing else
├── USAGE.md                          # install + CLI-only reference, no project background (M7 follow-up)
├── README.md
└── README.pt-BR.md                   # Portuguese-Brazil translation of README.md only (M7 follow-up); other docs stay English, linked as "(em inglês)"
```

---

## 4. Milestone status

| Milestone | Status | Scope |
|---|---|---|
| **M0** | ✅ done, committed, pushed | Repo bootstrap: pyproject.toml, CLI skeleton (`--version` only), CI, pre-commit, MIT license |
| **M1** | ✅ done, committed, pushed | Minimal pipeline: annotated `int` functions, `+ - *`, calls, `return`, `print`. Module top-level compiles to C++ `int main()`. |
| **M2** | ✅ done, committed, pushed | `if/elif/else`, `while`, `for ... in range(...)`, comparisons, `and/or/not`, local variables (plain + annotated assignment), flow-sensitive type joins, `BoolType` |
| **M3** | ✅ done, committed, pushed | `StringType`, `pyrt::Str` (UTF-8 bytes), string literals, `+` concatenation, string comparisons, f-strings (no `!conversion`/`:format_spec`), `print(str)` |
| **M4** | ✅ done, committed, pushed | `list`/`dict`/`set`/`tuple` literals, indexing (negative-index for list/tuple), `for x in <container>`, list comprehensions (range- and container-sourced, one optional `if`) |
| **M5** | ✅ done, committed, pushed | Classes, `__init__`, single inheritance, closed-world virtual dispatch (Decision D, §6, now implemented) and polymorphic assignment |
| **M6** | ✅ done, committed, pushed | Exceptions: `try`/`except`/`raise`, a curated `pyrt` exception hierarchy (Decision E, §6, now implemented), floor division (`//`) |
| **M7** | ✅ done, committed, pushed (`a26fbd9`) | v0.1.0 polish: `docs/architecture.md`, `docs/adding-python-feature.md`, `USAGE.md`, `README.pt-BR.md`, full example set, issue templates, CHANGELOG, CODE_OF_CONDUCT, cross-compiler CI validation, PyPI Trusted Publishing release workflow |

CI has been green through M2 on all 12 matrix jobs (ubuntu/macos/windows ×
py3.10–3.13); M3/M4/M5/M6 pass the full local acceptance suite (`ruff`,
`mypy --strict`, `pytest`, g++ compilation of every golden case) but
haven't had a CI run confirmed since pushing — check GitHub Actions status
before assuming green, per §2's "never claim a check passed without
running it." **M7 is the exception**: its CI/release changes actually
were confirmed with a real run — after pushing `a26fbd9`, both workflows
were watched to completion (`gh run watch ... --exit-status`) rather than
assumed. `ci.yml` run `32759687148`: all 12 matrix jobs green, and the new
`clang` install (Linux) / `ilammy/msvc-dev-cmd` setup (Windows) steps
worked, so the golden tests' `g++`/`clang++`/`cl` parametrization actually
exercised all three instead of skipping two of them on non-Linux jobs.
`release.yml` run `32759687152`: the `build` job (sdist + wheel +
`twine check`) passed; the `publish` job correctly stayed skipped, since
it's gated on a GitHub Release being published and this was a plain push.
**Still genuinely NOT RUN / needs external action**: PyPI Trusted
Publishing itself has never fired, because it needs a one-time step only
a human with PyPI account access can do — see §6's M7 scope-calls entry.

M7 added four new example programs (`examples/strings.py`,
`containers.py`, `classes.py`, `exceptions.py`) alongside the existing
`classify.py`. Each was actually transpiled, compiled with
`g++ -std=c++17 -Wall -Wextra` (zero warnings), run, and diffed against
plain CPython's stdout before being committed to the repo — the same
manual-smoke-test discipline every feature milestone has used, applied
here to documentation-facing code instead of a new language feature. Two
real mistakes this caught, worth remembering for future example/doc
writing: (1) an initial draft called `str(self.area())` as a normal
function call inside a class's `describe()` method — `str(...)` is only
ever synthesized internally by f-string lowering (`IRToStr`), not
recognized as a general user-callable, so this failed to lower; fixed by
using an f-string instead. (2) an initial `containers.py` printed a
`set[int]` directly in a spot where its element values didn't happen to
share CPython's actual (hash-based, unspecified) iteration order —
`pyrt::Set` is deliberately insertion-ordered (see §6/§8), a real,
already-accepted divergence from CPython for internal golden tests, but
one that's confusing to show off in a public-facing example without
comment; fixed by summing the set's contents (order-independent) instead
of printing it raw. `tests/cases/valid/containers.py`'s own golden
fixture prints a raw `set[int]` too and still passes only because its
specific small integer values happen to coincide with CPython's actual
iteration order for that dataset — that's a coincidence of the existing
fixture, not a guarantee; don't read it as evidence the ordering divergence
isn't real.

A follow-up commit after `a26fbd9` added two more documents, requested
directly rather than as part of the original M7 scope: `USAGE.md` (a
standalone install/CLI-only reference, deliberately kept separate from
`README.md` rather than replacing it, since `pyproject.toml`'s
`readme = "README.md"` field is also what PyPI shows as the project
description — a request for "usage-only instructions" isn't the same
request as "replace the project's PyPI-facing description") and
`README.pt-BR.md` (a Portuguese-Brazil translation of `README.md`, cross-
linked from the top of both files). **Scope note**: only `README.md` was
translated — `USAGE.md`, `docs/architecture.md`,
`docs/adding-python-feature.md`, and `CODE_OF_CONDUCT.md` are still
English-only, and `README.pt-BR.md`'s links to them say "(em inglês)"
rather than silently pointing a Portuguese reader at an English page with
no warning. If more translations are wanted later, keep that same
"linked page is English, and says so" pattern rather than either silently
mixing languages or half-translating a doc.

**Latest commits** (newest first): `a26fbd9` (M7: architecture docs,
examples, issue templates, CHANGELOG, CODE_OF_CONDUCT, cross-compiler CI,
PyPI Trusted Publishing release workflow), `08f87ea` (M6: exceptions,
try/except/raise, and floor division), `90ca2a4` (docs-only: mark M5
committed in HANDOFF.md), `69df8ad` (M5: classes, single inheritance, and
virtual dispatch), `411acf9` (M4: containers and comprehensions),
`f19eb43` (M3: strings and f-strings), `da8cccc` (CI-only fix: dropped a
non-portable stderr assertion — Clang's Windows runtime doesn't print the
same overflow message glibc's libstdc++ does; the actual safety
guarantee, a nonzero exit code, held everywhere).

A real bug M4's manual smoke-testing caught before it shipped: `std::vector
<bool>` is a bit-packed specialization whose element access returns a proxy
object, not a real `bool&`. That would have made `List<bool>::at()` return a
dangling reference (UB) and silently broken bool printing inside containers.
Fixed by backing `pyrt::List`/`pyrt::Set` with `std::deque` instead, which
has no such specialization for any element type. Lesson for future
milestones: **always compile and diff a real hand-written smoke-test program
against CPython before calling a milestone done**, not just rely on the unit
test suite — this class of bug is exactly the kind unit tests with mocked/
hand-built IR won't catch, since it only manifests when real generated code
actually gets compiled.

A real bug M5's manual smoke-testing caught before it shipped: `self` used
as a bare *value* (returned, stored into an attribute, passed as an
argument — not just `self.attr`/`self.method(...)`) emitted as raw C++
`this`, which either fails to compile against a `shared_ptr<T>`-typed
target or, if worked around with `std::enable_shared_from_this`, is
undefined behavior when called from inside the object's own constructor
(`shared_from_this()` cannot be used before `make_shared` finishes
establishing ownership). Fixed by rejecting `self` as a value everywhere
in `frontend/subset.py` — it may only ever be the receiver of `.attr`/
`.method(...)` — rather than trying to special-case constructor vs.
non-constructor methods. Same lesson as M4: this only surfaced by actually
compiling a hand-written smoke test (a self-referential linked-node class),
not from unit tests over hand-built IR.

A real bug M6's manual smoke-testing caught before it shipped: emitting a
`try` with more than one `except` clause produced mismatched braces --
each handler independently emitted both its own opening `'} catch (...) {'`
and a standalone closing `'}'`, so a second handler's opening brace tried
to close a block the first handler had already closed, and g++ failed with
a cascade of "expected unqualified-id before 'catch'" errors starting at
the *second* handler. Fixed by restructuring emission to match how
`_emit_if`'s `elif`-chain already merges braces: only the handler bodies
are indented/dedented per-handler, and exactly one standalone closing
brace is written once, after the last handler. Same lesson as M4/M5 (see
above): this shape is invisible to hand-built-IR unit tests unless the
test specifically has two-or-more handlers, and only actually fails at the
g++ compile step, not at the Python level.

---

## 5. Explicit non-goals (v1)

Metaclasses, arbitrary decorators, generators/`yield`, `async`/`await`,
`eval`/`exec`, unrestricted duck typing, monkey patching, dynamic class
mutation, unrestricted reflection, descriptors, advanced metaprogramming,
arbitrary dynamic imports, full CPython object model/ABI compatibility,
CPython extension modules.

---

## 6. Mandatory semantic decisions — status

These were flagged in the project brief as requiring explicit discussion
before their dependent architecture gets built. Status of each:

### Decision A — Python `int` representation: **DECIDED, implemented**
`std::int64_t`. All arithmetic (`+ - * //`) routes through
`pyrt::add/sub/mul/floordiv`, which check bounds *before* the operation
(portable, no compiler-specific `__builtin_*_overflow`) and throw on
overflow — never silently wraps, never relies on signed-overflow UB.
Overflow now throws `pyrt::OverflowError` (Decision E's exception
hierarchy, implemented in M6); it threw plain `std::overflow_error` from
M1 through M5, back when `pyrt` had no exception hierarchy of its own yet.

### Decision B — Python `str` / Unicode: **DECIDED, implemented**
`pyrt::Str` wraps a UTF-8 `std::string`. Per the approved scope for M3,
codepoint-aware indexing/length/iteration were **not** built yet (no
milestone needs them until containers/`len()` land) — M3 only needed
construction, `+` concatenation, comparison (byte-wise, which is provably
equivalent to codepoint order for valid UTF-8, so this is free and
correct), and streaming for `print`/f-strings. String *literals* in
generated C++ are escaped byte-by-byte via
`backend/string_literals.py::cpp_string_literal()` — every non-ASCII or
special byte becomes its own adjacent `"\xHH"` string-literal segment, so a
hex escape can never swallow a following character, and the exact UTF-8
bytes survive across GCC/Clang/MSVC without depending on any compiler's
source/execution charset.

### Decision C — container aliasing (list/dict/set): **DECIDED, implemented**
`pyrt::List`/`pyrt::Dict`/`pyrt::Set` each wrap a `std::shared_ptr` to
their backing storage. Assignment copies the `shared_ptr` (cheap, aliased —
matches Python's reference semantics). Scalars (int/bool/str) and `tuple`
(mapped to a genuine `std::tuple<...>`) stay true value types, as decided.
**Mutation itself (`.append()`, `d[k] = v`) is still not implemented** —
M4 only needed the storage shape to be aliasing-correct in advance so a
future mutation-adding milestone doesn't have to redesign every container
consumer; there was nothing to mutate yet, so the aliasing behavior itself
isn't observable until that lands.

### Decision D — class method dispatch: **DECIDED, implemented**
Whole-program (closed-world) class-hierarchy analysis: a method is emitted
`virtual` iff it's actually overridden somewhere in the compiled program
(computed, not user-declared — so no silent-divergence risk). Non-overridden
methods stay non-virtual for performance/readable output. This requires
committing to single-compilation-unit, closed-world class compilation as a
v1 limitation (documented, not silent).
`ir/lower.py::_compute_virtual_methods()` walks every class's own method
names up its base chain once, over the whole `SymbolTable`, before any
class body is lowered; a class gets `virtual ~ClassName() = default;` iff
it has a base or is itself someone's base. Alongside this, class instances
were given **reference semantics**: every class-typed variable, parameter,
attribute, or return value is `std::shared_ptr<ClassName>` (see
`backend/types_cpp.py`), matching Python's object-identity/aliasing
semantics the same way Decision C did for containers — `a = b` aliases,
mutating through one is visible through the other, and a base-typed
variable can hold a derived instance (the polymorphism this decision
exists to dispatch on). Construction (`Foo(args)`) compiles to
`std::make_shared<Foo>(args)`.

### Decision E — exception mapping: **DECIDED, implemented**
A curated (not exhaustive) `pyrt::PyException` hierarchy
(`semantic/exceptions.py::EXCEPTION_HIERARCHY` on the Python side,
`include/pyrt/exceptions.hpp` on the C++ side, kept in exact 1:1 sync):
`Exception` (root; maps to the actual C++ class `PyException`),
`ValueError`, `TypeError`, `RuntimeError`, `LookupError` →
{`IndexError`, `KeyError`}, `ArithmeticError` → {`ZeroDivisionError`,
`OverflowError`}. `except Foo:` → `catch (const pyrt::Foo&)`; `except Foo
as e:` binds `e`; multiple `except` clauses become one chained
try/catch (mirroring how `_emit_if` already chains `elif`); py2cpp itself
rejects a `try` whose earlier `except` clause would make a later one
unreachable (`P2C2004`, a new code — nothing existing fit this
"unreachable handler" diagnostic kind). Each exception carries one `Str`
message (`raise ValueError("msg")`); `.args`, `raise X from Y`, and
`finally` are all deferred (no C++ equivalent for `finally` without real
added complexity — an RAII scope-guard could do it later). An `except ...
as e:` binding is *not* a first-class value: `e` may only be passed
directly to `print(...)` or interpolated into an f-string (both go
through `pyrt::print`/`pyrt::str`'s existing generic dispatch once
`PyException` defines `operator<<`/`str()` overloads for itself) — never
stored in another variable, annotated as a parameter type, or compared;
see `types/model.py::ExceptionType`.

`List.at()`/`Dict.at()` and int overflow, previously documented
placeholders throwing plain `std::out_of_range`/`std::overflow_error`,
now throw `pyrt::IndexError`/`pyrt::KeyError`/`pyrt::OverflowError` — so
`except IndexError:` etc. actually catch what a user would expect. This
also motivated adding floor division (`//`, `pyrt::floordiv`, Python's
round-toward-negative-infinity semantics, not C++'s truncating `/`) as
part of M6: without it, `ZeroDivisionError` would have had nothing to
naturally trigger it (py2cpp still has no true `/`, since that needs
`FloatType`, which doesn't exist). User-defined classes subclassing a
builtin exception (e.g. `class ConfigError(ValueError): ...`, combining
M5's class hierarchy with this one) is explicitly deferred to a later
milestone — M5's and M6's inheritance systems don't interact yet.

### Additional decisions made during M2 (not in the original brief, surfaced by implementation)
- **bool/int join policy** (user-approved): `bool` widens to `int`
  one-way — in branch/loop type joins, in reassignment compatibility, and
  as arithmetic operands (`count + (a > 0)` works). `int` never narrows to
  `bool`. See `src/py2cpp/types/join.py`. As of M4 this also governs
  container-literal element-type unification: `[1, (2 > 1), 3]` widens to
  `list[int]`, so it prints `[1, 1, 3]`, not `[1, True, 3]` — a consistent
  application of the same rule, not a special case, but worth knowing if a
  test looks "wrong" at a glance.
- **Truthiness policy** (user-approved): `if`/`while` accept any `int`
  condition (0 = falsy), matching Python — implemented as a `pyrt`-free
  `(x != 0)` wrap (`IRTruthy` node), not a runtime helper.

### Scope calls made during M4 (flagged, not discussed in advance — all milestone-scoped per §2's carve-out)
- **`pyrt::Set` is insertion-ordered**, deduplicating by `==` at
  construction. CPython's actual set iteration order is hash-based and not
  part of the language's guaranteed semantics, so matching it byte-for-byte
  in golden tests would be unsound; py2cpp instead commits to a stronger,
  py2cpp-specific guarantee. Documented in `set.hpp`'s header comment.
- List comprehensions only — dict/set comprehensions deferred.
- `in`/`not in` deferred entirely.
- Tuple indexing requires a compile-time integer literal (`std::get<N>`
  needs one); tuple iteration and tuple-unpacking in a `for` target are
  deferred (tuple iteration needs compile-time loop unrolling, a
  genuinely different codegen shape than the uniform `for`/comprehension
  machinery this milestone built for list/dict/set).
- Empty list/dict/set literals are rejected (no element type to infer,
  and not very useful yet anyway since mutation isn't supported — an
  empty list you can never append to has limited value).

### Scope calls made during M5 (flagged, not discussed in advance — all milestone-scoped per §2's carve-out)
- **A class must define its own `__init__`** — constructors are not
  inherited. A subclass with a base always calls `super().__init__(...)`
  as `__init__`'s first statement (structurally required, mirrors C++'s
  own base-before-derived-body construction order); a class without a
  base has no such call.
- **An attribute (`self.x: T = value`) may only be declared as a direct,
  unconditional top-level statement of `__init__`** — never nested in an
  `if`/`while`/`for` there. Every declared attribute is therefore always
  initialized whenever `__init__` runs, matching a C++ struct member's
  "always exists" guarantee (every attribute member gets a `{}` default
  member initializer too, purely so no member is ever left indeterminate
  even transiently — not because the constructor body relies on it).
  Reassigning an *inherited* attribute with the same type from a
  subclass's `__init__` (e.g. `super().__init__()` sets a default, then
  the subclass overwrites it with a real value) is a normal reassignment,
  not a new field; giving it a **different** type is rejected
  (`DUPLICATE_DEFINITION`) since C++ can't have two same-named fields.
- **Attribute mutation (`obj.x = value`, including `self.x = value`) is
  supported anywhere**, unlike M4's container-mutation deferral — a plain
  struct-member assignment is far lower complexity than container
  `.append()`/`[]=`, and classes without it can barely hold state.
- **`self` may only ever be the receiver of `.attr`/`.method(...)`** —
  never returned, stored, passed as an argument, or otherwise used as a
  value. See the M5 smoke-test bug note above (§4) for why: methods are
  real C++ member functions, so `self` is C++'s raw `this`, and recovering
  a real `shared_ptr` to it via `std::enable_shared_from_this` is
  impossible from inside the object's own constructor — since `__init__`
  always maps to a constructor, allowing `self`-as-value in ordinary
  methods but not `__init__` would be a confusing asymmetry, so it's
  disallowed uniformly instead.
- **Only single inheritance**; no class variables, static/class methods,
  properties, operator-overload dunders, or dunder methods other than
  `__init__`; no `isinstance()`.
- **Comparing class instances (`==`, `<`, etc.) is rejected** — needs
  `__eq__`/`__lt__`-style dunder support, deferred along with the other
  operator-overload dunders.
- **Printing a class instance is rejected** — no `__repr__`/`__str__`
  protocol decided yet, so `print(some_object)` has no defined output
  rather than a guessed one.
- **A method must return a value**, exactly like a free function
  (`__init__` is the only exception — it never returns one); this
  sidesteps needing a `None`/void type this milestone, at the cost of no
  void-returning mutator methods (use attribute mutation directly, or a
  method that mutates *and* returns the new value, instead).
- **Class-typed elements aren't supported in container literals**
  (`[dog, cat]` for sibling subclasses `Dog`/`Cat` of `Animal`) — the
  container-literal element-type join (`types/join.py::join()`) was
  deliberately *not* extended with class-hierarchy awareness (that logic
  lives only in `ir/lower.py`'s `_assignable()`, which composes the pure
  primitive-coercion rules with class subtyping); a list/dict/set of
  polymorphic objects is a real, deferred gap, not an oversight.
- Forward/self/mutually-referencing class attribute types (e.g. a
  self-referential `Node` holding a `next: Node` field passed in from
  outside) work: every class name is forward-declared
  (`struct ClassName;`) before any full definition is emitted, and
  `std::shared_ptr<T>` only needs `T` to be a known type name, not a
  complete one, at the point of member declaration. Only *construction*
  (`Foo(args)`) and *base-class references* need `Foo` already fully
  defined earlier in the file (checked the same way a regular function
  call's definition-order is already checked) — plain type annotations
  don't, since Python only evaluates them when the method actually runs.
- No `Optional`/`None` for class types — meaning a genuinely
  null-terminated or cyclic structure (e.g. a linked list's tail) can't
  actually be built this milestone (every `Node` needs a *real* `next`).
  Not discovered until writing the manual smoke test; flagged here rather
  than worked around, since a workaround would just be `None` support by
  another name.

### Scope calls made during M6 (flagged, not discussed in advance — all milestone-scoped per §2's carve-out)
- **`try` supports one or more `except` clauses only** — no `try/else`,
  no `finally` (see Decision E above). Each `except` names at most one
  exception type (no `except (A, B):`) — separate `except` clauses cover
  it; this was a complexity/value tradeoff (supporting a tuple of types
  cleanly needs either N separate `catch` blocks sharing one body or a
  single `catch` on their common ancestor, neither trivial), not a
  fundamental limitation.
- **Bare `raise` (re-raise) may only appear lexically inside an `except`
  handler's body** — checked structurally in `frontend/subset.py` (a
  conservative approximation of Python's own dynamic "no active exception
  to re-raise" runtime error; conservative because it's a stricter,
  lexical version of Python's real dynamic-call-stack rule, so it can
  only reject programs Python would *also* reject, never accept one
  Python would reject). `raise X from Y` (cause chaining) isn't
  supported.
- **`raise` requires a direct `ExcType(...)` call naming a known,
  curated exception type** — `raise ValueError` (bare class, no call) and
  `raise some_variable` (raising an already-constructed exception value)
  are both rejected; exceptions aren't first-class values this milestone
  (see Decision E), so there's no way to hold one in a variable to raise
  later anyway.
- A name that collides with a curated exception type (e.g. `class
  ValueError: ...` or `def TypeError(): ...`) is rejected as a reserved
  name at symbol-collection time, the same as any other duplicate
  definition — avoids a genuinely confusing shadow between py2cpp's own
  vocabulary and user code.
- Comparing (`==`, `<`, etc.) two `ExceptionType` values is rejected, the
  same as comparing two class instances (M5) — no dunder support yet.

### Scope calls made during M7 (flagged, not discussed in advance — docs/tooling, not language-subset, but still worth flagging per §2's spirit)
- **`CODE_OF_CONDUCT.md`'s enforcement contact** was filled in with an
  email address rather than left as a placeholder or routed through
  GitHub Issues (which would make a conduct report public) — check that
  the address in the file is actually the one you want published before
  this gets pushed; it's easy to change and low-stakes since nothing is
  committed yet.
- **PyPI release trigger**: `.github/workflows/release.yml`'s `publish`
  job only runs on a GitHub Release being *published* (not a bare
  `git push --tags`) — the PyPA-recommended pattern, since cutting a
  Release is a deliberate, reviewable action distinct from pushing a tag.
  A separate `build` job (sdist + wheel + `twine check`) runs on every
  push to `main` and every PR, so packaging breakage is caught long
  before a real release attempt, without needing PyPI credentials to
  run it.
- **PyPI Trusted Publishing needs one external, one-time step this
  session cannot perform**: on pypi.org, under the `py2cpp` project's
  (once created) publishing settings, a maintainer must add a trusted
  publisher pointing at `edpl22/py2cpp`, workflow file `release.yml`,
  environment `pypi`. Until that's done, `release.yml`'s `publish` job
  will fail with an OIDC/authorization error the first time a Release is
  published — this is expected, not a bug in the workflow, and is exactly
  the kind of external account action that has to happen outside an
  agent session. The `py2cpp` name was confirmed available on PyPI
  (checked at write time — names can be claimed by someone else in the
  meantime, so re-check before the first real publish).
- **Cross-compiler CI**: `ci.yml` now explicitly installs `clang` on the
  Linux job (`apt-get install clang`) and sets up the MSVC dev environment
  on the Windows job (`ilammy/msvc-dev-cmd@v1`) so `tests/integration/
  test_golden.py`'s existing `g++`/`clang++`/`cl` parametrization actually
  exercises all three instead of skipping two of them. **Deliberately not
  done**: forcing a real GNU `g++` onto the macOS job via Homebrew (macOS's
  own `g++`/`gcc` are just aliases to Apple Clang) — `brew install gcc`
  is slow and would add real time to every cell of the OS × Python-version
  matrix for coverage that substantially overlaps with `clang++`, already
  exercised on that job. If cross-compiler coverage on macOS specifically
  becomes a priority, revisit this rather than assuming it was an
  oversight.
- Considered and rejected duplicating `tests/cases/valid/*.py` fixtures
  as the new `examples/*.py` files. The test fixtures are optimized for
  exhaustively exercising edge cases (single-element tuples, negative
  indexing, re-raise chains); the examples are meant to read as small,
  plausible programs a newcomer skims to understand *why* a feature is
  useful, so they were written fresh, narrower in scope, and specifically
  verified to match CPython's actual output (see §4's M7 entry for the
  two bugs that caught).

---

## 7. Current type system & IR (exact state)

**Types** (`types/model.py`): `Type` (base), `IntType`, `BoolType`,
`StringType`, `ListType(element_type)`, `DictType(key_type, value_type)`,
`SetType(element_type)`, `TupleType(element_types: tuple[Type, ...])`,
`ClassType(name)` (M5 — equality/hashing by name alone; the class's actual
shape lives in `SymbolTable`, not on the type itself), `ExceptionType(name)`
(M6 — same shape as `ClassType`, but deliberately not a first-class value
type; see the M6 entry in §6). `FloatType` doesn't exist yet — added only
when a milestone needs it. `types/join.py` stays hierarchy-agnostic (only
bool/int coercion); `ir/lower.py::_assignable()`/`_is_subclass()` are the
one place that additionally know about *class* subtyping (not exception
subtyping — that's a separate, simpler check, since `ExceptionType` values
never need assignability at all; see `semantic/exceptions.py`'s own
`is_exception_ancestor()`), composing the pure type-system rules with the
class hierarchy — see the M5 entry in §6.

**Symbols** (`semantic/symbols.py`, M5 additions): `AttributeSymbol`,
`MethodSymbol` (like `FunctionSymbol` but excludes `self`, whose type is
always implicitly the enclosing class), `ClassSymbol` (`name`, `base:
str | None`, `init_parameters`, `attributes`/`methods` dicts holding only
members declared *directly* on that class — a lookup that needs the full
base-aware member set walks the base chain via `SymbolTable.classes`, see
`ir/lower.py::_resolve_attribute()`/`_resolve_method()`). `collect.py`
gathers every class *name* in one pass before resolving any annotation, so
a self- or forward-referencing attribute type (e.g. `self.next: Node`)
resolves even though `Node` isn't finished being defined yet.

**Exception registry** (`semantic/exceptions.py`, new in M6): a fixed,
py2cpp-internal `EXCEPTION_HIERARCHY: dict[str, str | None]` (name →
parent name) mirroring a curated subset of Python's builtins — *not*
collected from source the way `ClassSymbol`/`FunctionSymbol` are, since
users can't define new exception types yet (see §6). `is_known_exception()`,
`is_exception_ancestor()`, and `cpp_exception_name()` (the one name that
doesn't map to itself: `"Exception"` → `"PyException"`, the actual C++
root class name) are the only three operations anything else needs from
this module — `ir/lower.py`, `ir/validate.py`, `backend/emit_cpp.py`, and
`semantic/collect.py` (to reserve these names against user redefinition)
all import from here rather than duplicating the hierarchy.

**IR nodes** (`ir/nodes.py`):
- Expressions: `IRLiteral` (int), `IRStringLiteral`, `IRToStr` (Python
  `str()` conversion for f-string interpolation, backed by `pyrt::str()`),
  `IRVarRef`, `IRBinaryExpr` (+/-/*, and string `+` concatenation),
  `IRCompare` (==,!=,<,<=,>,>=), `IRLogicalExpr` (and/or, bool-only
  operands), `IRNot`, `IRTruthy` (int→bool for conditions), `IRCall`,
  `IRListLiteral`, `IRDictLiteral`, `IRSetLiteral`, `IRTupleLiteral`,
  `IRIndex` (list `[i]` / dict `[k]`, runtime index, emits `.at(...)`),
  `IRTupleIndex` (tuple `[i]`, compile-time-resolved position, emits
  `std::get<N>(...)`), `IRListCompRange` (comprehension over `range(...)`),
  `IRListCompForEach` (comprehension over a container), `IRAttributeAccess`
  (`obj.attr` read, M5), `IRMethodCall` (`obj.method(args)`, M5),
  `IRConstruct` (`ClassName(args)`, backed by `std::make_shared`, M5).
  `BinaryOp` gained `FLOORDIV` in M6 (`a // b`, backed by `pyrt::floordiv`)
  alongside the existing `ADD`/`SUB`/`MUL`.
- Statements: `IRReturn`, `IRPrintStmt`, `IRExprStmt`, `IRAssign` (with a
  `declare: bool` flag), `IRIf`, `IRWhile`, `IRFor` (raw int range loop),
  `IRForEach` (`for x in <container>`; binds `.first` for a `dict`, since
  Python dict iteration yields keys only), `IRAttributeAssign` (`obj.attr
  = value`, M5 — used for both a constructor's first-time attribute init
  and any later mutation; no `declare` flag, since the C++ struct member
  already exists as part of the class's own shape by the time any
  statement runs). M6 additions: `IRRaise` (`exception_type: str | None`,
  `message: IRExpr | None` — both `None` together means a bare re-raise,
  `exception_type` set with `message` `None` means `raise Foo()`),
  `IRTry` (`body`, `handlers: tuple[IRExceptHandler, ...]`) and
  `IRExceptHandler` (`exception_type: str | None` — `None` is a bare
  `except:`, `bound_name: str | None`, `body`).
- `IRFunction`; M5 additions: `IRAttribute` (name+type), `IRMethod` (like
  `IRFunction` plus `is_virtual`/`is_override`, computed not user-declared
  — see Decision D in §6), `IRConstructor` (`base_args: tuple[IRExpr,...]
  | None` for the `super().__init__(...)` call, emitted into C++'s
  member-initializer-list since a base subobject can only be constructed
  there, never as an ordinary body statement), `IRClassDef` (`name`,
  `base`, `attributes`, `constructor`, `methods`,
  `needs_virtual_destructor`)
- `IRModule` (now also carries `classes: tuple[IRClassDef, ...]`)

**Diagnostic scheme** (`codes.py`): `P2C1xxx` = frontend/subset shape,
`P2C2xxx` = semantic/name resolution, `P2C3xxx` = type checking, `P2C9xxx`
= internal compiler error (a py2cpp bug, never a user error). Full current
list: `SYNTAX_ERROR` (1000), `UNSUPPORTED_SYNTAX` (1001),
`MISSING_ANNOTATION` (1002), `UNDEFINED_NAME` (2001),
`DUPLICATE_DEFINITION` (2002), `UNKNOWN_CALL_TARGET` (2003),
`UNREACHABLE_EXCEPT_CLAUSE` (2004, **new in M6** — no existing code fit
"this except clause can never fire" cleanly), `TYPE_MISMATCH` (3001),
`ARGUMENT_COUNT_MISMATCH` (3002), `INTERNAL_ERROR` (9001). M3/M4/M5/M6
otherwise reused existing codes rather than adding new ones (e.g. an
f-string `!conversion` is `UNSUPPORTED_SYNTAX`; a tuple out-of-range
index is `TYPE_MISMATCH`; a class missing `__init__` is
`UNSUPPORTED_SYNTAX`; an unknown attribute/method or unknown exception
type is `UNDEFINED_NAME`/`UNKNOWN_CALL_TARGET`; a used-before-defined base
class is `UNDEFINED_NAME`, mirroring the existing "function used before
defined" check).

---

## 8. Deliberate scoping restrictions currently in force

These are real, documented gaps versus full Python — not oversights. Each
is flagged in the relevant module's docstring too. A future milestone can
lift any of these; none are architectural dead ends.

- **`return` may only be the final statement of a function's own top-level
  body** — never nested inside `if`/`while`/`for`, never more than once.
  No early/multiple return points yet.
- **A local variable's declaring assignment must occur at the same block
  level as every place that reads it.** A name first assigned inside an
  `if`/`elif`/`else` — even in *every* branch — does not survive past that
  block (Python would allow this; py2cpp currently doesn't). Workaround:
  pre-declare it before the conditional (`result: int = 0` then reassign
  inside branches). This sidesteps hoisting a C++ declaration out of
  branches that might disagree on type.
- **Chained comparisons rejected** (`a < b < c`) — naive translation would
  silently compute `(a<b)<c` instead of Python's `(a<b) and (b<c)`.
- **`and`/`or`/`not` require `bool` operands** — not Python's general
  "returns one of the operands" semantics (which would need either
  double-evaluating the left operand or a temporary-variable mechanism the
  current expression-only IR doesn't have).
- **`for` loop's `step` must be a compile-time integer literal** (e.g.
  `-2` is fine, a variable isn't) — lets the loop direction (`<` vs `>`)
  be chosen statically.
- **No general unary minus** — only literal negation (`-5`) is recognized;
  `-x` for an arbitrary expression `x` is rejected (needs overflow-checked
  negation with an `INT64_MIN` edge case, not yet built).
- **Module top-level and function bodies share one statement-lowering
  path** (`ir/lower.py::_lower_block`/`_lower_stmt`) — this was a
  deliberate unification, not an accident.
- **f-strings don't support `!conversion` (`!r`/`!s`/`!a`) or
  `:format_spec`** — rejected explicitly (`UNSUPPORTED_SYNTAX`) rather
  than silently ignored or mistranslated.
- **`pyrt::Str` has no indexing/length/iteration yet** — only whole-string
  construction, `+`, comparison, and streaming. Deferred to whichever
  milestone first needs `len()`/subscripting a string.
- **No container mutation** — no `.append()`, no `d[k] = v`, no `.add()`
  for sets. Containers are built via literals/comprehensions only and read
  via indexing/iteration.
- **No `in`/`not in`.**
- **List comprehensions only** — no dict/set comprehensions yet, and only
  one `for` clause / at most one `if` clause per comprehension (no
  nested/multi-clause comprehensions).
- **Tuple indexing requires a compile-time integer literal** (`t[0]`, not
  `t[i]`) — `std::get<N>` needs a compile-time index.
- **Tuples can't be iterated or unpacked** (`for x in t`, `a, b = t`) —
  deferred; would need compile-time loop unrolling, a different codegen
  shape than list/dict/set iteration.
- **Empty list/dict/set literals are rejected** — no element type to infer
  from zero elements, and no annotation-driven type hint is threaded in.
- **`pyrt::Set`'s iteration order is insertion order**, not CPython's
  actual (unspecified, hash-based) order — see §6.
- Only `g++` (MSYS2) is available on the local dev machine — `clang++` and
  `cl.exe` (MSVC) are not, so those compiler paths are only exercised by
  CI, never locally. Keep this in mind when a "works on my machine" claim
  needs cross-checking; trust CI's green checkmarks over local-only runs
  for compiler-specific behavior.

M5's and M6's own scoping restrictions (classes/inheritance/`self`;
`try`/`except`/`raise`) are listed in their own "Scope calls made during
M5/M6" subsections under §6 rather than duplicated here, since each is
tightly coupled to the semantic decision it was made alongside.

---

## 9. How to build & verify (exact commands that must all pass)

```bash
# one-time setup
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1   |   Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# acceptance suite (must all be run for real before any milestone is called done)
ruff check .
mypy --strict src tests
pytest
```

Manual smoke test:
```bash
py2cpp examples/classify.py -o build/ --emit-runtime
g++ -std=c++17 build/classify.cpp -o build/classify
./build/classify
```

**Do this for every new milestone, not just the example above**: hand-write
a small Python program exercising the milestone's new feature(s), run it
through `py2cpp ... -o <dir> --emit-runtime`, compile the output with
`g++ -std=c++17 -Wall -Wextra` (zero warnings is the bar, not just "it
compiles"), run it, and diff its stdout against `python <same file>`. M4's
`std::vector<bool>` bug (§4) only surfaced this way — the hand-built-IR unit
tests couldn't have caught it.

GitHub CLI is installed and authenticated in this environment
(`C:\Program Files\GitHub CLI\gh.exe`, account `edpl22`) — use it for CI
status, not guessing.

Packaging check (mirrors `.github/workflows/release.yml`'s `build` job;
**not yet run in this environment** — `build`/`twine` are CI-only tooling,
not part of `requirements.txt`, so this is NOT RUN until someone actually
runs it, in CI or in a disposable venv, not the project's own `.venv`):
```bash
python -m pip install build twine   # in a disposable venv, not .venv
python -m build
twine check dist/*
```

---

## 10. What to tell a fresh Claude Code session

If you're starting a brand-new chat: paste the **original project brief**
(the full `py2cpp` specification with all 42 sections — milestones,
architecture rules, absolute development rules) as the first message if
you still have it, since it's the authoritative source for rules this
document only summarizes. Then say something like:

> M0 through M6 are implemented, committed, and pushed to
> https://github.com/edpl22/py2cpp; M7 (v0.1.0 polish) is implemented
> locally but not yet committed — read `HANDOFF.md` in the repo root for
> exact current state, including the two external/unverified items under
> §6's "Scope calls made during M7" (PyPI trusted-publisher setup, a real
> CI run confirming the new cross-compiler steps). Once M7 is committed,
> pushed, and CI-confirmed, the project has no further milestone defined
> yet — decide the post-v0.1.0 roadmap with the user rather than
> inventing one (candidates already flagged as open gaps: container
> mutation, `in`/`not in`, user-defined exception subclasses,
> `Optional`/`None` for class types — see §5/§6/§8).

If you don't have the original brief anymore, this document plus a look at
the actual repo (`git log`, `src/py2cpp/`, `tests/`) should be enough for
Claude to reconstruct working context — the code itself is heavily
commented with the *why*, not just the *what*, specifically so it's
self-explaining to a fresh reader.
