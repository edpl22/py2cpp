"""Command-line interface for py2cpp.

The full flag surface documented in the project's CLI contract is declared
here now so the interface is stable for scripts and CI from day one. Only
``--version`` is functionally implemented in this milestone; the compiler
pipeline (frontend through backend) lands starting in M1.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from py2cpp import __version__

_LOG = logging.getLogger("py2cpp")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py2cpp",
        description="Transpile a Python 3.10+ subset to C++17.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"py2cpp {__version__}",
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="Python source file to transpile.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory for generated C++ files.",
    )
    parser.add_argument(
        "--emit-runtime",
        action="store_true",
        help="Copy the pyrt header-only runtime alongside the generated output.",
    )
    parser.add_argument(
        "--std",
        choices=["c++17", "c++20"],
        default="c++17",
        help="Target C++ standard for the generated code (default: c++17).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run validation and type checking without emitting C++ files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (debug-level) logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if args.source is None:
        parser.print_help(sys.stderr)
        return 2

    _LOG.error(
        "py2cpp does not yet support transpilation (the compiler pipeline "
        "lands in milestone M1); only --version is currently implemented."
    )
    return 1
