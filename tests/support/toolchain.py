"""Discovers and drives C++ compilers for integration/golden tests.

Never hardcodes a compiler path -- toolchains are located with
shutil.which so tests behave correctly on whatever machine runs them, and
a missing compiler is reported as skipped (NOT RUN), never faked.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INCLUDE_DIR = _REPO_ROOT / "include"


@dataclass(frozen=True)
class Toolchain:
    name: str
    executable: Path

    def compile(
        self, sources: list[Path], output: Path, *, std: str = "c++17"
    ) -> subprocess.CompletedProcess[str]:
        if self.name == "cl":
            args = [
                str(self.executable),
                f"/std:{std}",
                "/EHsc",
                "/nologo",
                f"/I{INCLUDE_DIR}",
                *(str(s) for s in sources),
                f"/Fe:{output}",
            ]
        else:
            args = [
                str(self.executable),
                f"-std={std}",
                "-O0",
                "-Wall",
                f"-I{INCLUDE_DIR}",
                *(str(s) for s in sources),
                "-o",
                str(output),
            ]
        return subprocess.run(args, capture_output=True, text=True)


def discover_toolchains() -> dict[str, Toolchain]:
    found: dict[str, Toolchain] = {}
    for name in ("g++", "clang++", "cl"):
        path = shutil.which(name)
        if path is not None:
            found[name] = Toolchain(name=name, executable=Path(path))
    return found
