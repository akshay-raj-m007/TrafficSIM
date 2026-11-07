"""The stored validation results (``data/validation.json``), served by ``GET /api/validation``.

Precomputed by ``tools/gen_validation.py``; nothing is measured at request time. The file is
*stale* when the engine source changed since it was generated (``tests/test_validation_doc.py``
fails, like the shipped experiments).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from trafficsim.engine.sourcedigest import source_digest

PATH: Final[Path] = Path(__file__).resolve().parents[1] / "data" / "validation.json"
FORMAT_VERSION: Final[int] = 1


def current_stamp() -> dict:
    return {"source_digest": source_digest(), "format_version": FORMAT_VERSION}


def stored() -> dict | None:
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else None


def is_stale(doc: dict) -> bool:
    return doc.get("stamp") != current_stamp()
