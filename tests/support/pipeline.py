"""Helpers shared by integration and golden tests: running CPython and
driving the py2cpp public API without going through the CLI subprocess.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from py2cpp.compiler import CompilationResult, CompilerOptions, compile_source


def run_python(source: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(source)], capture_output=True, text=True)


def transpile(source: Path, output_dir: Path, *, emit_runtime: bool = False) -> CompilationResult:
    options = CompilerOptions(source=source, output=output_dir, emit_runtime=emit_runtime)
    return compile_source(options)
