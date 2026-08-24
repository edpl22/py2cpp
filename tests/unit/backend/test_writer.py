from __future__ import annotations

import pytest

from py2cpp.backend.writer import CodeWriter


def test_write_line_indents_according_to_depth() -> None:
    writer = CodeWriter()
    writer.write_line("int main() {")
    writer.indent()
    writer.write_line("return 0;")
    writer.dedent()
    writer.write_line("}")

    assert writer.render() == "int main() {\n    return 0;\n}\n"


def test_blank_write_line_is_not_indented() -> None:
    writer = CodeWriter()
    writer.indent()
    writer.write_line()

    assert writer.render() == "\n"


def test_dedent_without_matching_indent_raises() -> None:
    writer = CodeWriter()
    with pytest.raises(RuntimeError):
        writer.dedent()
