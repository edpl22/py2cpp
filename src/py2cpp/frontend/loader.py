"""Reads Python source files from disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    path: Path
    text: str


class SourceLoadError(Exception):
    """Raised when a source file cannot be read from disk.

    Deliberately not a Diagnostic: without readable source there is no
    text to anchor a SourceLocation to. The CLI boundary turns this into a
    clean top-level message instead.
    """


def load_source(path: Path) -> SourceFile:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SourceLoadError(f"cannot read '{path}': {exc.strerror or exc}") from exc
    return SourceFile(path=path, text=text)
