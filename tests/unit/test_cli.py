"""Tests for the py2cpp CLI entry point."""

from __future__ import annotations

import subprocess
import sys

import pytest

from py2cpp import __version__
from py2cpp.cli import main


def test_version_flag_prints_version_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_module_entry_point_reports_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py2cpp", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert __version__ in result.stdout


def test_no_source_argument_exits_with_usage_status() -> None:
    assert main([]) == 2
