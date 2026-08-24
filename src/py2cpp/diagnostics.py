"""Diagnostics: source locations, severities, and the engine that collects
compiler-reported problems for a single compilation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


@dataclass(frozen=True)
class SourceLocation:
    """A single point in a source file, 1-indexed to match editor conventions."""

    filename: Path
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.filename}:{self.line}:{self.column}"


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    severity: Severity
    code: str
    message: str
    location: SourceLocation
    help_text: str | None = None

    def format(self) -> str:
        header = f"{self.location}: {self.severity.value}[{self.code}]: {self.message}"
        if self.help_text is None:
            return header
        return f"{header}\nhelp: {self.help_text}"


class DiagnosticEngine:
    """Accumulates diagnostics for one compilation.

    Stages report through this rather than printing directly, so multiple
    problems within a single stage (e.g. several unsupported nodes) can be
    surfaced together instead of stopping at the first one.
    """

    def __init__(self) -> None:
        self._diagnostics: list[Diagnostic] = []

    def error(
        self,
        code: str,
        message: str,
        location: SourceLocation,
        help_text: str | None = None,
    ) -> None:
        self._diagnostics.append(Diagnostic(Severity.ERROR, code, message, location, help_text))

    def warning(
        self,
        code: str,
        message: str,
        location: SourceLocation,
        help_text: str | None = None,
    ) -> None:
        self._diagnostics.append(Diagnostic(Severity.WARNING, code, message, location, help_text))

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return list(self._diagnostics)

    @property
    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self._diagnostics)
