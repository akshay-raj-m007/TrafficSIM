"""Module-boundary rule: the engine and network packages are pure.

They may import only the standard library, NumPy, and each other — never FastAPI,
pydantic, the server package, or anything UI-related.
"""

import ast
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "trafficsim"
PURE_PACKAGES = ("engine", "network")
ALLOWED_THIRD_PARTY = {"numpy"}
ALLOWED_INTERNAL = {"trafficsim.engine", "trafficsim.network"}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg_parts = ["trafficsim", *path.relative_to(PKG).parent.parts]
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # resolve relative import against the file's package
                base = pkg_parts[: len(pkg_parts) - node.level + 1]
                mods.append(".".join(base + ([node.module] if node.module else [])))
            else:
                mods.append(node.module or "")
    return mods


def _allowed(mod: str) -> bool:
    top = mod.split(".")[0]
    if top == "trafficsim":
        return any(mod == p or mod.startswith(p + ".") for p in ALLOWED_INTERNAL)
    return top in sys.stdlib_module_names or top in ALLOWED_THIRD_PARTY or top == "__future__"


FILES = sorted(f for p in PURE_PACKAGES for f in (PKG / p).rglob("*.py"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(PKG)))
def test_pure_packages_import_only_stdlib_numpy_and_each_other(path):
    bad = [m for m in _imports(path) if not _allowed(m)]
    assert not bad, f"{path.name} imports forbidden modules: {bad}"


def test_rule_catches_violations():
    assert not _allowed("fastapi")
    assert not _allowed("trafficsim.server.app")
    assert _allowed("numpy.random") and _allowed("dataclasses")
