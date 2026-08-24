"""Wraps ast.parse, translating SyntaxError into a Diagnostic instead of
letting it escape as a raw Python exception.
"""

from __future__ import annotations

import ast

from py2cpp import codes
from py2cpp.diagnostics import DiagnosticEngine, SourceLocation
from py2cpp.frontend.loader import SourceFile


def parse_source(source: SourceFile, diagnostics: DiagnosticEngine) -> ast.Module | None:
    try:
        return ast.parse(source.text, filename=str(source.path))
    except SyntaxError as exc:
        location = SourceLocation(
            filename=source.path,
            line=exc.lineno or 1,
            column=exc.offset or 1,
        )
        diagnostics.error(codes.SYNTAX_ERROR, exc.msg, location)
        return None
