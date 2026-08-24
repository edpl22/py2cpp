from __future__ import annotations

from py2cpp.backend.mangling import escape_identifier


def test_plain_identifier_is_unchanged() -> None:
    assert escape_identifier("add") == "add"


def test_cpp_keyword_gets_trailing_underscore() -> None:
    assert escape_identifier("class") == "class_"
    assert escape_identifier("new") == "new_"
    assert escape_identifier("template") == "template_"


def test_escaped_keyword_can_never_collide_with_a_real_keyword() -> None:
    for keyword in ("class", "new", "template", "private", "public", "delete"):
        assert escape_identifier(keyword) != keyword
