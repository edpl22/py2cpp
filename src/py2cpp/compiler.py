"""Orchestrates the full compilation pipeline and exposes it as a
reusable, thin public API independent of the CLI (see cli.py).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from py2cpp.backend.emit_cpp import emit_module
from py2cpp.diagnostics import Diagnostic, DiagnosticEngine
from py2cpp.frontend.loader import load_source
from py2cpp.frontend.parser import parse_source
from py2cpp.frontend.subset import validate_subset
from py2cpp.ir.lower import lower_module
from py2cpp.ir.validate import validate_module
from py2cpp.semantic.collect import collect_symbols

_PYRT_SOURCE_DIR = Path(__file__).resolve().parent.parent.parent / "include" / "pyrt"


@dataclass(frozen=True)
class CompilerOptions:
    source: Path
    output: Path | None = None
    std: str = "c++17"
    emit_runtime: bool = False
    check_only: bool = False


@dataclass(frozen=True)
class CompilationResult:
    success: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    cpp_path: Path | None = None


def compile_source(options: CompilerOptions) -> CompilationResult:
    """Run the full pipeline for a single source file.

    Raises frontend.loader.SourceLoadError if the source file itself can't
    be read, and ir.validate.InternalCompilerError if the IR fails its
    final invariant checks (always a py2cpp bug). Every other failure --
    anything caused by the user's program -- is reported through the
    returned CompilationResult's diagnostics instead of raising.
    """

    diagnostics = DiagnosticEngine()

    source = load_source(options.source)

    tree = parse_source(source, diagnostics)
    if tree is None:
        return CompilationResult(success=False, diagnostics=diagnostics.diagnostics)

    validate_subset(tree, source, diagnostics)
    if diagnostics.has_errors:
        return CompilationResult(success=False, diagnostics=diagnostics.diagnostics)

    symtab = collect_symbols(tree, source, diagnostics)
    if diagnostics.has_errors:
        return CompilationResult(success=False, diagnostics=diagnostics.diagnostics)

    ir_module = lower_module(tree, symtab, source, diagnostics)
    if ir_module is None:
        return CompilationResult(success=False, diagnostics=diagnostics.diagnostics)

    validate_module(ir_module)

    if options.check_only:
        return CompilationResult(success=True, diagnostics=diagnostics.diagnostics)

    cpp_text = emit_module(ir_module)
    output_dir = options.output if options.output is not None else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    cpp_path = output_dir / f"{ir_module.name}.cpp"
    cpp_path.write_text(cpp_text, encoding="utf-8")

    if options.emit_runtime:
        shutil.copytree(_PYRT_SOURCE_DIR, output_dir / "pyrt", dirs_exist_ok=True)

    return CompilationResult(success=True, diagnostics=diagnostics.diagnostics, cpp_path=cpp_path)
