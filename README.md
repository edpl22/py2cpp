# py2cpp

This is a vibe-coded project motivated by curiosity of the capabilities of AI.

A transpiler that translates a well-defined subset of **Python 3.10+** into
readable, compilable **C++17**. py2cpp is itself written entirely in Python;
C++ is only ever an output format, plus a small header-only compatibility
runtime (`pyrt`) linked by generated code.

> **Status:** M4 complete. py2cpp compiles functions with annotated `int`/
> `bool`/`str`/`list`/`dict`/`set`/`tuple`, arithmetic, comparisons,
> `and`/`or`/`not`, local variables, `if`/`elif`/`else`, `while`,
> `for ... in range(...)` and `for ... in <container>`, string
> concatenation, f-strings, list/dict/set/tuple literals, indexing, and
> list comprehensions to compilable C++17. Container mutation
> (`.append(...)`, `d[k] = v`), `in`/`not in`, dict/set comprehensions,
> and tuple iteration/unpacking aren't supported yet. See the roadmap
> below for what's not there yet.

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
(coming in a later milestone) for the full design rationale.

## Installation

py2cpp is not yet published. Once released:

```bash
pip install py2cpp
```

## Development setup

```bash
git clone <this-repository>
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

## Roadmap

| Milestone | Scope |
|---|---|
| M0 | Repository bootstrap, CLI skeleton, CI |
| M1 | Minimal functions/arithmetic pipeline: Python → AST → IR → C++ → compiled → run |
| M2 | Control flow (`if`/`while`/`for`) and static type inference — **done** |
| M3 | Strings and f-strings — **done** |
| M4 | Containers (`list`/`dict`/`set`/`tuple`) and comprehensions — **done** |
| M5 | Classes and single inheritance |
| M6 | Exceptions |
| M7 | v0.1.0 polish: docs, examples, cross-compiler CI, packaging |

## License

[MIT](LICENSE)
