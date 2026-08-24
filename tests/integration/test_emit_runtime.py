"""Regression coverage for --emit-runtime producing a truly self-contained
output directory.

This specifically compiles with no -I flag at all (unlike the golden
harness, which always passes -I<repo>/include): pyrt's own headers must
resolve each other via sibling-relative #include, not "pyrt/..."-prefixed
paths, or they break once copied to <output>/pyrt/ with nothing to fall
back on. A prior version of pyrt.hpp got this wrong and only golden tests
(which always pass -I) caught the working case, not the self-contained
one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.support.pipeline import run_python, transpile
from tests.support.toolchain import discover_toolchains

_SOURCE = Path(__file__).resolve().parent.parent / "cases" / "valid" / "add.py"
_TOOLCHAINS = discover_toolchains()


@pytest.mark.parametrize("compiler_name", ["g++", "clang++", "cl"])
def test_emit_runtime_output_compiles_without_include_flags(
    compiler_name: str, tmp_path: Path
) -> None:
    toolchain = _TOOLCHAINS.get(compiler_name)
    if toolchain is None:
        pytest.skip(f"{compiler_name} not found on PATH (NOT RUN)")

    compile_result = transpile(_SOURCE, tmp_path, emit_runtime=True)
    assert compile_result.success, "\n".join(d.format() for d in compile_result.diagnostics)
    assert compile_result.cpp_path is not None
    assert (tmp_path / "pyrt" / "pyrt.hpp").exists()

    binary = tmp_path / ("program.exe" if compiler_name == "cl" else "program")
    if compiler_name == "cl":
        args = [
            str(toolchain.executable),
            "/std:c++17",
            "/EHsc",
            "/nologo",
            str(compile_result.cpp_path),
            f"/Fe:{binary}",
        ]
    else:
        args = [
            str(toolchain.executable),
            "-std=c++17",
            "-O0",
            str(compile_result.cpp_path),
            "-o",
            str(binary),
        ]
    build = subprocess.run(args, capture_output=True, text=True, cwd=tmp_path)
    assert build.returncode == 0, build.stderr

    run_result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run_result.stdout == run_python(_SOURCE).stdout
