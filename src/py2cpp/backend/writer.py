"""A small, deterministic line-oriented C++ code writer.

Keeps emission from degrading into uncontrolled string concatenation:
callers write logical lines and manage nesting with indent()/dedent(), and
CodeWriter is solely responsible for consistent, deterministic formatting.
"""

from __future__ import annotations

_INDENT_UNIT = "    "


class CodeWriter:
    def __init__(self) -> None:
        self._lines: list[str] = []
        self._depth = 0

    def write_line(self, text: str = "") -> None:
        if text:
            self._lines.append(f"{_INDENT_UNIT * self._depth}{text}")
        else:
            self._lines.append("")

    def indent(self) -> None:
        self._depth += 1

    def dedent(self) -> None:
        if self._depth == 0:
            raise RuntimeError("CodeWriter.dedent() called with no matching indent()")
        self._depth -= 1

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"
