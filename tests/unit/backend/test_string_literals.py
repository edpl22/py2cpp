from __future__ import annotations

from py2cpp.backend.string_literals import cpp_string_literal


def test_plain_ascii_text_is_a_single_segment() -> None:
    assert cpp_string_literal("hello") == '"hello"'


def test_empty_string() -> None:
    assert cpp_string_literal("") == '""'


def test_quote_and_backslash_are_escaped() -> None:
    assert cpp_string_literal('a"b\\c') == '"a" "\\""' + ' "b" "\\\\"' + ' "c"'


def test_newline_tab_and_carriage_return_use_short_escapes() -> None:
    assert cpp_string_literal("a\nb\tc\rd") == '"a" "\\n"' + ' "b" "\\t"' + ' "c" "\\r"' + ' "d"'


def test_non_ascii_bytes_are_isolated_hex_escapes() -> None:
    # 'e9' is Latin-1 e-acute (U+00E9), which UTF-8-encodes to 0xC3 0xA9.
    result = cpp_string_literal("café")
    assert result == '"caf" "\\xc3" "\\xa9"'


def test_isolated_hex_escapes_prevent_swallowing_a_following_hex_digit() -> None:
    # If '\xc3' and a following literal 'a' were emitted in the same
    # segment, C++ would parse '\xc3a' as one (wrong) hex escape instead of
    # the byte 0xC3 followed by the letter 'a'.
    result = cpp_string_literal("éa")
    assert result == '"\\xc3" "\\xa9" "a"'
