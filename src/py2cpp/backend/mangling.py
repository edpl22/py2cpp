"""Deterministic escaping for Python identifiers that collide with a C++
keyword.

py2cpp requires a whole-program, closed-world view of the compiled source
(see the class-dispatch design notes), so every identifier the backend
emits is known statically; escaping is applied uniformly rather than left
to chance.
"""

from __future__ import annotations

_CPP_KEYWORDS = frozenset(
    {
        "alignas", "alignof", "and", "and_eq", "asm", "atomic_cancel",
        "atomic_commit", "atomic_noexcept", "auto", "bitand", "bitor",
        "bool", "break", "case", "catch", "char", "char8_t", "char16_t",
        "char32_t", "class", "compl", "concept", "const", "consteval",
        "constexpr", "constinit", "const_cast", "continue", "co_await",
        "co_return", "co_yield", "decltype", "default", "delete", "do",
        "double", "dynamic_cast", "else", "enum", "explicit", "export",
        "extern", "false", "float", "for", "friend", "goto", "if",
        "inline", "int", "long", "mutable", "namespace", "new",
        "noexcept", "not", "not_eq", "nullptr", "operator", "or",
        "or_eq", "private", "protected", "public", "reflexpr",
        "register", "reinterpret_cast", "requires", "return", "short",
        "signed", "sizeof", "static", "static_assert", "static_cast",
        "struct", "switch", "synchronized", "template", "this",
        "thread_local", "throw", "true", "try", "typedef", "typeid",
        "typename", "union", "unsigned", "using", "virtual", "void",
        "volatile", "wchar_t", "while", "xor", "xor_eq",
    }
)  # fmt: skip


def escape_identifier(name: str) -> str:
    """Escape a Python identifier into a always-safe, valid C++ identifier.

    C++ keywords get a trailing underscore. Since C++ never spells its own
    keywords with a trailing underscore, this can never collide with a
    real one, and is applied deterministically (the same input always
    escapes the same way).
    """

    if name in _CPP_KEYWORDS:
        return f"{name}_"
    return name
