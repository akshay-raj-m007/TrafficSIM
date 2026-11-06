"""Code rule: each source file stays under ~200 lines (blank and comment-only lines
excluded, matching the frontend's ESLint ``max-lines`` settings)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 200
FILES = sorted([*(ROOT / "trafficsim").rglob("*.py"), *(ROOT / "tests").rglob("*.py")])


def _code_lines(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    return sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_file_is_short(path):
    n = _code_lines(path)
    assert n <= MAX_LINES, f"{path.name} has {n} code lines (limit {MAX_LINES})"
