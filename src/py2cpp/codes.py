"""Central registry of py2cpp diagnostic codes.

Numbering scheme:
    1xxx - frontend: syntax errors and unsupported-subset shape
    2xxx - semantic analysis: name resolution and symbol table
    3xxx - type checking
    9xxx - internal compiler errors (a py2cpp bug, never a user error)
"""

from __future__ import annotations

SYNTAX_ERROR = "P2C1000"
UNSUPPORTED_SYNTAX = "P2C1001"
MISSING_ANNOTATION = "P2C1002"

UNDEFINED_NAME = "P2C2001"
DUPLICATE_DEFINITION = "P2C2002"
UNKNOWN_CALL_TARGET = "P2C2003"

TYPE_MISMATCH = "P2C3001"
ARGUMENT_COUNT_MISMATCH = "P2C3002"

INTERNAL_ERROR = "P2C9001"
