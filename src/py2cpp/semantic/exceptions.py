"""The curated, fixed set of exception types py2cpp knows how to raise and
catch (the M6 project-brief decision, "Decision E").

Unlike user-defined classes (semantic/symbols.py's ClassSymbol), this
hierarchy is not collected from source -- it is a static, py2cpp-internal
registry mirroring a subset of Python's builtin exception types, growing on
demand as later milestones need more of them. 'Exception' stands in for
Python's own Exception, the practical root for everything user code raises
or catches; BaseException-only cases like KeyboardInterrupt/SystemExit are
out of scope and never modeled.

User-defined classes subclassing one of these (e.g. a custom
'ConfigError(ValueError)') are deferred to a later milestone -- this
milestone's exception hierarchy and M5's user-class hierarchy are two
separate, non-interacting systems for now.
"""

from __future__ import annotations

EXCEPTION_HIERARCHY: dict[str, str | None] = {
    "Exception": None,
    "ValueError": "Exception",
    "TypeError": "Exception",
    "RuntimeError": "Exception",
    "LookupError": "Exception",
    "IndexError": "LookupError",
    "KeyError": "LookupError",
    "ArithmeticError": "Exception",
    "ZeroDivisionError": "ArithmeticError",
    "OverflowError": "ArithmeticError",
}


def is_known_exception(name: str) -> bool:
    return name in EXCEPTION_HIERARCHY


def is_exception_ancestor(name: str, ancestor: str) -> bool:
    """True if 'ancestor' is 'name' itself or a type 'name' derives from."""

    current: str | None = name
    while current is not None:
        if current == ancestor:
            return True
        current = EXCEPTION_HIERARCHY[current]
    return False


def cpp_exception_name(name: str) -> str:
    """'Exception' maps to pyrt::PyException, the actual root class name;
    every other curated name maps to itself.
    """

    return "PyException" if name == "Exception" else name
