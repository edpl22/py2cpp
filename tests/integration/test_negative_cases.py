"""Negative tests: everything under tests/cases/invalid/ must fail with
exactly the diagnostic code declared in its .json sidecar.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from py2cpp.compiler import CompilerOptions, compile_source

_CASES_DIR = Path(__file__).resolve().parent.parent / "cases" / "invalid"


def _case_paths() -> list[Path]:
    return sorted(_CASES_DIR.glob("*.py"))


@pytest.mark.parametrize("source", _case_paths(), ids=lambda p: p.stem)
def test_invalid_case_reports_expected_diagnostic(source: Path) -> None:
    sidecar = json.loads(source.with_suffix(".json").read_text(encoding="utf-8"))
    expected_code = sidecar["code"]

    result = compile_source(CompilerOptions(source=source, check_only=True))

    assert not result.success
    codes_seen = [d.code for d in result.diagnostics]
    assert expected_code in codes_seen, codes_seen
