# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project intends to adhere to [Semantic Versioning](https://semver.org/)
once it reaches 1.0.0. Before then, minor versions may include breaking
changes to the supported Python subset or generated C++ shape.

## [Unreleased]

### Added

- `docs/architecture.md` and `docs/adding-python-feature.md`.
- Example programs for strings, containers, classes, and exceptions
  under `examples/`.
- Issue templates, `CODE_OF_CONDUCT.md`, and this changelog.
- A PyPI Trusted Publishing release workflow.

## [0.1.0] - Unreleased

The first tagged release. Compiles the subset of Python 3.10+ described in
the README to compilable, warning-clean C++17.

### Added

- Annotated functions over `int`/`bool`/`str`/`list`/`dict`/`set`/`tuple`,
  arithmetic (`+ - * //`) with overflow checking, comparisons, `and`/`or`/
  `not`, local variables, `if`/`elif`/`else`, `while`,
  `for ... in range(...)` and `for ... in <container>`.
- String concatenation and f-strings (no `!conversion` or `:format_spec`).
- `list`/`dict`/`set`/`tuple` literals, indexing, and list comprehensions.
- Classes: `__init__`, single inheritance, closed-world virtual dispatch,
  reference-semantic instances.
- Exceptions: `try`/`except`/`raise` against a curated `pyrt` exception
  hierarchy.
- A header-only C++ runtime (`pyrt`) covering strings, containers, print/
  repr formatting, overflow-checked arithmetic, and exceptions.
- A `P2C####` diagnostic scheme with precise source locations and, where
  applicable, actionable `help:` text.
- CI across ubuntu/macos/windows and Python 3.10–3.13, running `ruff`,
  `mypy --strict`, and `pytest` (including golden-case compilation against
  every C++ compiler found on `PATH`).
