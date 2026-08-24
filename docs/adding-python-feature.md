# Adding a Python feature

This is a checklist-style walkthrough for adding new Python syntax or
semantics to py2cpp. Read [`architecture.md`](architecture.md) first if
you haven't — this document assumes you know what each package in
`src/py2cpp/` is responsible for.

The running example below is a *hypothetical* feature — adding `len()`
for `str`/`list`/`dict`/`set` — chosen because it touches nearly every
layer without being so large it obscures the shape of the change. You
won't need every step for every feature (a purely structural restriction
might only touch `frontend/subset.py`), but working through them in order
is the safest way not to miss one.

## 0. Decide the scope, out loud, before writing code

Before touching any code, write down — in the PR description or an issue,
not just in your head — exactly what's in scope and what isn't. For
`len()`: does it work on all four container-ish types, or just some this
milestone? Does it accept an arbitrary expression, or only a variable?

Two categories of scope decision get different treatment (see
`HANDOFF.md` §2 in the repository root for the full rule, if it's still
present at the time you're reading this):

- **A project-wide semantic decision** (does py2cpp's `int` wrap or throw
  on overflow? are containers reference- or value-typed?) needs to be
  discussed with a maintainer before implementation — options, pros/cons,
  a recommendation — not decided silently inside a PR.
- **A small, reversible, feature-scoped restriction** ("`len()` only
  accepts a bare variable, not an arbitrary expression, for now") is fine
  to decide unilaterally, as long as it's clearly flagged in the PR
  description, not silently applied.

When in doubt about which category a decision falls into, treat it as the
first kind.

## 1. Frontend: is the syntax shape allowed at all?

`frontend/subset.py` answers "is this *shape* of syntax something py2cpp
is willing to look at?" — structurally, on the raw `ast.AST`, before any
name resolution or type checking. For `len(...)`, this is where you'd
confirm the call has exactly one argument, if that's the scope decided in
step 0.

Get this step right and wrong: a shape rejected here fails fast with a
clean diagnostic. A shape *not* rejected here that the rest of the
pipeline doesn't actually handle risks failing later with a confusing
error, or — far worse — an `InternalCompilerError` if it slips all the way
to `ir/validate.py`. When in doubt, reject explicitly and narrow the scope
rather than letting an edge case fall through.

## 2. Semantic layer: does this need a new symbol or annotation shape?

Most features don't touch `semantic/`. You'd come here if the feature
introduces a new kind of name to track (`semantic/symbols.py`,
`semantic/collect.py`) or a new shape of type annotation
(`semantic/annotations.py`). `len()` doesn't need any of this — it's a
call to a builtin, not a new declaration shape.

## 3. Types: does this need a new `Type`, or a new join/assignability rule?

`len()` returns `int` — an existing `Type` — so this step is a no-op for
the running example. If your feature needs a genuinely new type
(`FloatType`, say), it goes in `types/model.py`, and any new coercion
rule between it and existing types goes in `types/join.py`. Keep
`join.py` hierarchy-agnostic: if your rule needs to know about class or
exception subtyping, it belongs in `ir/lower.py`'s `_assignable()`
instead, composed with the primitive rules, not folded into `join.py`
itself.

## 4. IR: add the node(s) that represent this

Add whatever new frozen dataclass(es) `ir/nodes.py` needs. For `len()`,
that's a single new expression node, say `IRLen(target: IRExpr)`. Keep IR
nodes minimal and typed — they should carry exactly the information the
backend needs to emit correct C++, no more (the backend must never need
to re-derive anything the IR could have told it directly).

## 5. Lowering: name resolution + type checking + IR construction

`ir/lower.py` is where the call actually gets recognized, its argument
type-checked (does `len()`'s target actually resolve to one of the
allowed container-ish types?), and the `IRLen` node built. This is also
where you'd emit a `Diagnostic` — with a precise `SourceLocation` and a
`P2C####` code — for any input that fails your step-0 scope decision
(`len(42)`, if `int` isn't a valid target, say).

If an entirely new *kind* of failure doesn't fit any existing code in
`codes.py`, add a new one there rather than force-fitting an unrelated
existing code — see `codes.py`'s own scheme comment for the numbering
convention (`P2C1xxx` frontend, `P2C2xxx` semantic, `P2C3xxx` type
checking).

## 6. Validate: no changes usually needed

`ir/validate.py` is a generic invariant checkpoint, not something you
typically add feature-specific logic to. It exists to catch a *bug* in
step 5's bookkeeping, not to duplicate step 5's own type checking. You'd
only touch it if your feature introduces a new structural invariant that
should hold for every well-formed IR tree (not just the common case).

## 7. Backend: emit the C++

`backend/emit_cpp.py` turns your new IR node into text — for `IRLen`,
something like emitting `.size()` (or a `pyrt` helper, if the direct C++
member function name isn't right for every target type). Remember: the
backend is a pure, mechanical translator. If you find yourself writing an
`if` here that re-derives something semantic ("is this actually a valid
target for `len()`?"), that check is misplaced — it belongs in step 5, and
by the time the backend sees the IR node, the answer should already be
baked into it.

## 8. Runtime (`pyrt`): only if C++ needs new library support

If the feature needs a runtime helper that doesn't already exist in
`include/pyrt/`, add it there — header-only, minimal, and only the shape
the feature actually needs (`len()` for `pyrt::Str` might need one, if
`pyrt::Str` doesn't already expose a byte-length accessor by the time you
read this). Keep `pyrt::pyrt.hpp`'s include order in mind — see its own
header comment.

## 9. Tests

Add, at minimum:

- **Unit tests** in `tests/unit/<matching-subpackage>/` for whichever
  layers you touched — a subset-validator test, a lowering test with
  hand-built IR expectations, a backend-emission test.
- **A golden case**: a `.py` fixture under `tests/cases/valid/` (either a
  new file or an addition to an existing one) whose CPython stdout the
  compiled C++ must match exactly. This is what `tests/integration/
  test_golden.py` runs against every C++ compiler it finds on `PATH`
  (skipping, never faking, whichever it doesn't).
- **A negative case**, if your feature rejects any input: a `.py` fixture
  under `tests/cases/invalid/` plus its `.json` sidecar naming the
  expected `P2C####` code.

## 10. The step unit tests can't replace: a real manual smoke test

Every milestone shipped so far (see `HANDOFF.md`'s milestone notes, if
still present) has caught at least one real bug — a `std::vector<bool>`
proxy-reference issue, an unusable `this` where a `shared_ptr` was
needed, mismatched braces across multiple `catch` handlers — that unit
tests over hand-built IR could not have caught, because the bug only
existed in the interaction between real generated code and a real C++
compiler.

Before calling any feature done:

```bash
py2cpp your_smoke_test.py -o build/ --emit-runtime
g++ -std=c++17 -Wall -Wextra build/your_smoke_test.cpp -o build/your_smoke_test
./build/your_smoke_test
python your_smoke_test.py   # diff this stdout against the line above
```

Zero warnings is the bar, not just "it compiles." If you don't have every
compiler locally (this project's own dev machine only has `g++` — see
`HANDOFF.md` §8), trust CI's green checkmarks for the compilers you can't
run, and say so explicitly rather than claiming a check passed that you
never ran.

## 11. Update the docs that describe current state

- `README.md`'s status line/roadmap table and restrictions list, if the
  feature changes what py2cpp currently supports.
- This repository's running project-memory document (`HANDOFF.md`, if
  still in use at the time you're reading this) — milestone status, any
  new IR nodes/diagnostic codes, and any scope calls made along the way
  (step 0's second category).

Then report status honestly (including any check you genuinely couldn't
run), propose a commit message, and stop for review before starting the
next feature — see this project's standing process rules for why.
