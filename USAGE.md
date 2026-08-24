# Using py2cpp

Instructions for installing py2cpp and transpiling a Python file to C++.
For what py2cpp is, what it supports, and how it's built, see
[`README.md`](README.md).

## Install

py2cpp isn't published yet. Until it is, install it from source:

```bash
git clone https://github.com/edpl22/py2cpp.git
cd py2cpp

python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

You'll also need a C++17 compiler on your `PATH` to build the generated
code — `g++`, `clang++`, or MSVC's `cl` all work.

## Transpile a file

```bash
py2cpp path/to/program.py -o build/ --emit-runtime
```

This writes `build/program.cpp`, plus a copy of the `pyrt` header-only
runtime it depends on (from `--emit-runtime`). Omit `--emit-runtime` if
you already have `pyrt`'s headers available on your include path some
other way.

## Compile and run the output

```bash
g++ -std=c++17 build/program.cpp -o build/program
./build/program
```

Any C++17 compiler works the same way, e.g.:

```bash
clang++ -std=c++17 build/program.cpp -o build/program
cl /std:c++17 /EHsc build\program.cpp
```

## CLI reference

```
py2cpp [-h] [--version] [-o OUTPUT] [--emit-runtime]
       [--std {c++17,c++20}] [--check] [--verbose]
       [source]
```

| Flag | Meaning |
|---|---|
| `source` | Python source file to transpile. |
| `-o`, `--output OUTPUT` | Output directory for the generated `.cpp` file. |
| `--emit-runtime` | Also copy the `pyrt` header-only runtime into the output directory. |
| `--std {c++17,c++20}` | Target C++ standard for the generated code (default: `c++17`). |
| `--check` | Run validation and type checking only — reports diagnostics without writing any C++ file. Useful in a pre-commit hook or CI step. |
| `--verbose` | Enable verbose (debug-level) logging. |
| `--version` | Print the py2cpp version and exit. |
| `-h`, `--help` | Show the CLI help and exit. |

## When py2cpp rejects your program

py2cpp only accepts a specific, explicitly-scoped subset of Python (see
`README.md`'s Restrictions section). A program outside that subset is
rejected with a diagnostic, not silently mistranslated:

```
program.py:12:9: error[P2C1001]: 'return' may only appear as the final statement of a function body in this milestone
help: early/multiple return points arrive in a later milestone
```

The message tells you exactly what construct isn't supported and where;
the optional `help:` line, when present, suggests a next step.

## Try it

```bash
py2cpp examples/classify.py -o build/ --emit-runtime
g++ -std=c++17 build/classify.cpp -o build/classify
./build/classify
```

More examples, each focused on one area of the language (strings,
containers, classes, exceptions), are in [`examples/`](examples/).
