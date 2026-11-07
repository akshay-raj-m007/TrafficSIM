"""Hash of the engine and network source files.

Cached comparison runs and the shipped experiment results are only valid for the code that
produced them. Their keys include this digest, so changing engine or network logic (not just a
constant) makes old entries miss. Line endings are normalised to LF so that a Windows checkout
(CRLF) and a Linux one (LF) give the same digest.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

_PACKAGES = ("engine", "network")
_CRLF, _LF = bytes([13, 10]), bytes([10])


def digest_of(root: Path) -> str:
    """Digest of the engine and network packages under ``root`` (the trafficsim directory)."""
    h = hashlib.sha256()
    for pkg in _PACKAGES:
        for path in sorted((root / pkg).rglob("*.py")):
            h.update(path.relative_to(root).as_posix().encode())
            h.update(path.read_bytes().replace(_CRLF, _LF))
    return h.hexdigest()


@lru_cache(maxsize=1)
def source_digest() -> str:
    return digest_of(Path(__file__).resolve().parents[1])
