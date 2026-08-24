"""Type join and assignability rules.

join() answers "what single type can represent either of these" for
merging branches of control flow (see ir/lower.py's handling of
if/elif/else). is_assignable() answers "can a value of this type be
stored into a variable already fixed at that type" for (re)assignment
compatibility.

Per the project's bool/int decision: bool widens to int (mirroring
CPython, where bool is literally an int subclass) but never the reverse,
so join is not symmetric in general -- only its *result* is order
independent. Once more types exist (float, str, ...), most pairs will
simply be incompatible (join returns None) rather than gaining ad hoc
coercions; each new coercion is a deliberate, documented decision, not a
default.
"""

from __future__ import annotations

from py2cpp.types.model import BoolType, IntType, Type


def join(a: Type, b: Type) -> Type | None:
    if a == b:
        return a
    if isinstance(a, IntType) and isinstance(b, BoolType):
        return a
    if isinstance(a, BoolType) and isinstance(b, IntType):
        return b
    return None


def is_assignable(value_type: Type, target_type: Type) -> bool:
    """True if a value of value_type can be stored into a variable already
    fixed at target_type, without target_type needing to widen."""

    return join(value_type, target_type) == target_type
