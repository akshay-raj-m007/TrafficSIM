"""On-disk cache of measured reference tables (saturation flows, free-flow times).

Committed tables cover the demo network with the default mix. Anything else (a non-default
vehicle mix, a changed lane structure) is measured once and stored here, keyed by the same
input digest that guards the committed tables (the digest includes the mix), so the same mix or
structure is never measured twice on a machine, and worker processes reuse what another
process measured. The directory comes from the TRAFFICSIM_TABLE_CACHE environment variable
(set by the server, inherited by worker processes); without it nothing is stored.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ENV_VAR = "TRAFFICSIM_TABLE_CACHE"


def cache_dir() -> Path | None:
    v = os.environ.get(ENV_VAR)
    return Path(v) if v else None


def _path(kind: str, digest: str) -> Path | None:
    d = cache_dir()
    return None if d is None else d / f"{kind}-{digest[:40]}.json"


def load(kind: str, digest: str) -> dict | None:
    p = _path(kind, digest)
    if p is None or not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # a torn or unreadable file is just a miss
    return doc if doc.get("digest") == digest else None


def store(kind: str, digest: str, doc: dict) -> None:
    p = _path(kind, digest)
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(p)  # atomic: readers never see a half-written file
