"""Golden tests: for every case under tests/cases/valid, CPython's own
stdout is the oracle. We transpile, compile with whatever C++ compiler is
available, run the result, and the two must match exactly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.support.pipeline import run_python, transpile
from tests.support.toolchain import discover_toolchains

_CASES_DIR = Path(__file__).resolve().parent.parent / "cases" / "valid"
_TOOLCHAINS = discover_toolchains()


def _case_paths() -> list[Path]:
    return sorted(_CASES_DIR.glob("*.py"))


@pytest.mark.parametrize("compiler_name", ["g++", "clang++", "cl"])
@pytest.mark.parametrize("source", _case_paths(), ids=lambda p: p.stem)
def test_golden_case(source: Path, compiler_name: str, tmp_path: Path) -> None:
    toolchain = _TOOLCHAINS.get(compiler_name)
    if toolchain is None:
        pytest.skip(f"{compiler_name} not found on PATH (NOT RUN)")

    python_result = run_python(source)
    assert python_result.returncode == 0, python_result.stderr

    compile_result = transpile(source, tmp_path)
    assert compile_result.success, "\n".join(d.format() for d in compile_result.diagnostics)
    assert compile_result.cpp_path is not None

    binary = tmp_path / ("program.exe" if compiler_name == "cl" else "program")
    build = toolchain.compile([compile_result.cpp_path], binary, std="c++17")
    assert build.returncode == 0, build.stderr

    run_result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run_result.stdout == python_result.stdout
    assert run_result.returncode == python_result.returncode
