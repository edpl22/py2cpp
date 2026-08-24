"""Escapes a Python str into a portable C++ string literal.

The text is stored as UTF-8 (see the project's Unicode policy decision), so
this must reproduce the exact UTF-8 bytes regardless of which of GCC,
Clang, or MSVC compiles the output -- relying on the compiler's own source
encoding/execution charset for non-ASCII characters is not portable across
those three.

Instead, every byte outside the safe printable-ASCII range is emitted as
its own adjacent-string-literal segment containing a single '\\xHH' escape
(e.g. '"caf" "\\xc3" "\\xa9"'). Isolating each hex escape in its own segment
matters because C++ hex escapes are unbounded: '\\xc3a9' would try to
consume 'a9' as further hex digits of the same escape instead of starting
the next byte. Adjacent string literals concatenate at compile time, so the
result is one pyrt::Str construction with the exact original UTF-8 bytes.
"""

from __future__ import annotations

_SHORT_ESCAPES: dict[int, str] = {
    0x22: '"\\""',
    0x5C: '"\\\\"',
    0x0A: '"\\n"',
    0x09: '"\\t"',
    0x0D: '"\\r"',
}


def cpp_string_literal(value: str) -> str:
    """Render value as one or more adjacent double-quoted C++ literals."""

    raw = value.encode("utf-8")
    segments: list[str] = []
    current = ""

    for byte in raw:
        if 0x20 <= byte <= 0x7E and byte not in _SHORT_ESCAPES:
            current += chr(byte)
            continue
        if current:
            segments.append(f'"{current}"')
            current = ""
        segments.append(_SHORT_ESCAPES.get(byte, f'"\\x{byte:02x}"'))

    if current:
        segments.append(f'"{current}"')
    if not segments:
        return '""'
    return " ".join(segments)
