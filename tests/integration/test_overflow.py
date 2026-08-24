"""Verifies Decision A's overflow-safety promise: int64 arithmetic
overflow must raise, never silently wrap or invoke undefined behavior.

CPython's int is arbitrary-precision and would not overflow computing
this, so unlike the golden tests this deliberately does not compare
against CPython's stdout -- it verifies py2cpp's own documented, loud
divergence (raise instead of a silently wrong number) instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.support.pipeline import transpile
from tests.support.toolchain import discover_toolchains

_TOOLCHAINS = discover_toolchains()

_OVERFLOWING_SOURCE = """\
def add(a: int, b: int) -> int:
    return a + b


print(add(9223372036854775807, 1))
"""


@pytest.mark.parametrize("compiler_name", ["g++", "clang++", "cl"])
def test_int64_addition_overflow_raises(compiler_name: str, tmp_path: Path) -> None:
    toolchain = _TOOLCHAINS.get(compiler_name)
    if toolchain is None:
        pytest.skip(f"{compiler_name} not found on PATH (NOT RUN)")

    source = tmp_path / "overflow.py"
    source.write_text(_OVERFLOWING_SOURCE, encoding="utf-8")

    compile_result = transpile(source, tmp_path)
    assert compile_result.success, "\n".join(d.format() for d in compile_result.diagnostics)
    assert compile_result.cpp_path is not None

    binary = tmp_path / ("program.exe" if compiler_name == "cl" else "program")
    build = toolchain.compile([compile_result.cpp_path], binary, std="c++17")
    assert build.returncode == 0, build.stderr

    run_result = subprocess.run([str(binary)], capture_output=True, text=True)
    # An uncaught C++ exception terminates the process abnormally on every
    # platform, but *how* -- exit code, and whether anything readable
    # lands on stderr -- is compiler/runtime-specific: glibc's libstdc++
    # prints "terminate called after throwing..." with the exception's
    # what(), but Clang's Windows runtime does not, so asserting on
    # stderr content isn't portable. The nonzero exit code is the actual,
    # portable guarantee: overflow was caught and raised, not silently
    # wrapped into a wrong answer.
    assert run_result.returncode != 0
