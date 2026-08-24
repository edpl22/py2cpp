# py2cpp

*Read this in other languages: [Português (Brasil)](README.pt-BR.md).*

This is a vibe-coded project motivated by curiosity of the capabilities of AI.

A transpiler that translates a well-defined subset of **Python 3.10+** into
readable, compilable **C++17**. py2cpp is itself written entirely in Python;
C++ is only ever an output format, plus a small header-only compatibility
runtime (`pyrt`) linked by generated code.

> **Status:** M0–M7 complete (v0.1.0 polish landed; not yet published to
> PyPI — see [Installation](#installation)). py2cpp compiles functions
> with annotated `int`/`bool`/`str`/`list`/`dict`/`set`/`tuple`,
> arithmetic (including overflow-checked `//`), comparisons, `and`/`or`/
> `not`, local variables, `if`/`elif`/`else`, `while`,
> `for ... in range(...)` and `for ... in <container>`, string
> concatenation, f-strings, list/dict/set/tuple literals, indexing, list
> comprehensions, classes with single inheritance and virtual dispatch,
> and `try`/`except`/`raise` against a curated exception hierarchy — all
> to compilable, warning-clean C++17, verified across
> ubuntu/macos/windows × Python 3.10–3.13 in CI, and against `g++`,
> `clang++`, and MSVC's `cl`. Container mutation (`.append(...)`,
> `d[k] = v`), `in`/`not in`, dict/set comprehensions, tuple
> iteration/unpacking, and user-defined exception subclasses aren't
> supported yet. See [Restrictions](#restrictions) and the roadmap below
> for what's not there yet.

## Why not just use Python?

You're not choosing py2cpp over Python; you're choosing it for the specific
cases where you need a small, statically-typed subset of a Python program
compiled to a native C++17 binary. It is not a general-purpose Python
implementation.

## Non-goals

py2cpp deliberately does **not** attempt to support:

- metaclasses, arbitrary decorators, descriptors, or dynamic class mutation
- generators / `yield`, coroutines, `async`/`await`
- `eval`, `exec`, or other dynamic code execution
- unrestricted duck typing, monkey patching, or reflection
- arbitrary/dynamic imports or third-party CPython extension modules
- full CPython object-model or ABI compatibility

Programs that require these constructs are rejected with a diagnostic, not
silently mistranslated. See [`docs/architecture.md`](docs/architecture.md)
for the full design rationale, and
[`docs/adding-python-feature.md`](docs/adding-python-feature.md) if you're
looking to contribute a new feature.

## Installation

py2cpp is not yet published. Once released:

```bash
pip install py2cpp
```

## Development setup

```bash
git clone https://github.com/edpl22/py2cpp.git
cd py2cpp

python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

All Python dependencies are installed through `requirements.txt` only —
never via individual `pip install <package>` commands.

Run the checks:

```bash
ruff check .
mypy --strict src tests
pytest
```

## Quick start

```bash
py2cpp examples/classify.py -o build/ --emit-runtime
g++ -std=c++17 build/classify.cpp -o build/classify
./build/classify
```

For just the install and CLI instructions, without any of the project
background on this page, see [`USAGE.md`](USAGE.md).

See [`examples/`](examples/) for more: [`strings.py`](examples/strings.py),
[`containers.py`](examples/containers.py), [`classes.py`](examples/classes.py),
and [`exceptions.py`](examples/exceptions.py) each focus on one area of the
supported subset. Every example is compiled with `g++ -Wall -Wextra` and its
output diffed against plain CPython as part of keeping this README honest.

## Restrictions

py2cpp's core rule is that it never guesses when Python semantics can't be
reproduced safely in C++ — it rejects the program with a diagnostic
instead. The restrictions below are real, deliberate scope limits, not
oversights; each can be lifted in a future milestone. The most notable:

- No container mutation yet (`.append(...)`, `d[k] = v`, `.add(...)`) —
  containers are built via literals/comprehensions and read via
  indexing/iteration only.
- No `in`/`not in`.
- List comprehensions only (no dict/set comprehensions), one `for` clause
  and at most one `if` clause each.
- Tuple indexing requires a compile-time integer literal; tuples can't be
  iterated or unpacked.
- No early or multiple `return` points — `return` may only be a
  function's final top-level statement.
- Chained comparisons (`a < b < c`) are rejected, not mistranslated.
- No `Optional`/`None` for class-typed values, so a genuinely
  null-terminated or cyclic structure can't be built yet.
- User-defined exception subclasses aren't supported; exceptions are
  matched against a fixed, curated hierarchy
  (`ValueError`/`TypeError`/`RuntimeError`/`LookupError` →
  `IndexError`/`KeyError`/`ArithmeticError` →
  `ZeroDivisionError`/`OverflowError`).
- `try` supports `except` clauses but not `finally` or `try`/`else`.
- Only single inheritance; no class variables, static/class methods,
  properties, or operator-overload dunders.

See [`docs/architecture.md`](docs/architecture.md) for the design
rationale behind these, and open an issue using the feature-request
template if one of them is blocking you.

## Roadmap

| Milestone | Scope |
|---|---|
| M0 | Repository bootstrap, CLI skeleton, CI — **done** |
| M1 | Minimal functions/arithmetic pipeline: Python → AST → IR → C++ → compiled → run — **done** |
| M2 | Control flow (`if`/`while`/`for`) and static type inference — **done** |
| M3 | Strings and f-strings — **done** |
| M4 | Containers (`list`/`dict`/`set`/`tuple`) and comprehensions — **done** |
| M5 | Classes and single inheritance — **done** |
| M6 | Exceptions — **done** |
| M7 | v0.1.0 polish: docs, examples, cross-compiler CI, packaging — **done** |

## Contributing

Issues and pull requests are welcome. Please read
[`docs/adding-python-feature.md`](docs/adding-python-feature.md) before
proposing a new language feature, and note the [Restrictions](#restrictions)
above — many gaps are deliberate scope decisions, not oversights, so it
helps to check whether one is already tracked before opening an issue.
This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE)
