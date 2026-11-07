"""The built-in experiments: precomputed, shipped with the app, served instantly.

    policy_rush    Webster vs pure max-pressure vs thresholded max-pressure, rush hour
    flyover_rush   flyover open vs closed (from the start), rush hour

Parameters are fixed here, before any result was seen: 10 paired runs, seeds 1-10, 900 s,
warm-up 300 s, default model. ``tools/gen_experiments.py`` runs them and writes
``trafficsim/data/experiments/<id>.json`` (every comparison plus the run-level results).
A stored file is *stale* when the model digest or the metric definitions changed since it
was generated; the API says so and ``tests/test_experiments.py`` fails.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Final

from trafficsim.engine.runmetrics import METRICS_VERSION
from trafficsim.server.compare_spec import DEFAULT_DURATION_S, DEFAULT_WARMUP_S, model_digest
from trafficsim.server.presets_doc import preset

DATA_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "data" / "experiments"
RUNS: Final[int] = 10
BASE_SEED: Final[int] = 1


def _rush(name: str, *, policy: str = "fixed_webster", flyover_open: bool = True) -> dict:
    doc = preset("rush_hour")
    doc["name"] = name
    doc["initial"]["policy"] = policy
    doc["initial"]["flyover_open"] = flyover_open
    return doc


def definitions() -> dict[str, dict]:
    webster = _rush("Webster", policy="fixed_webster")
    mp = _rush("Max-pressure", policy="max_pressure")
    mpt = _rush("Thresholded max-pressure", policy="max_pressure_threshold")
    return {
        "policy_rush": {
            "title": "Signal policy at rush hour",
            "description": "Webster (fixed-time) against pure max-pressure and thresholded "
            "max-pressure at J1, rush-hour demand (every flow x1.31). Difference = B - A.",
            "comparisons": [
                ("Webster vs max-pressure", webster, mp),
                ("Webster vs thresholded max-pressure", webster, mpt),
                ("Max-pressure vs thresholded max-pressure", mp, mpt),
            ],  # fmt: skip
        },
        "flyover_rush": {
            "title": "Flyover open vs closed at rush hour",
            "description": "The flyover open against closed from the start, rush-hour demand. "
            "Difference = closed - open.",
            "comparisons": [
                (
                    "Flyover open vs closed",
                    _rush("Flyover open"),
                    _rush("Flyover closed", flyover_open=False),
                )
            ],  # fmt: skip
        },
    }


def request_for(a: dict, b: dict) -> dict:
    return {"a": deepcopy(a), "b": deepcopy(b), "runs": RUNS, "duration_s": DEFAULT_DURATION_S,
            "warmup_s": DEFAULT_WARMUP_S, "base_seed": BASE_SEED}  # fmt: skip


def current_stamp() -> dict:
    return {"model_digest": model_digest(2), "metrics_version": METRICS_VERSION}


def stored(exp_id: str) -> dict | None:
    p = DATA_DIR / f"{exp_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def is_stale(doc: dict) -> bool:
    return doc.get("stamp") != current_stamp()


def listing() -> list[dict]:
    out = []
    for exp_id, d in definitions().items():
        doc = stored(exp_id)
        out.append({"id": exp_id, "title": d["title"], "description": d["description"],
                    "available": doc is not None, "stale": None if doc is None else is_stale(doc),
                    "comparisons": [c[0] for c in d["comparisons"]],
                    "params": {"runs": RUNS, "duration_s": DEFAULT_DURATION_S,
                               "warmup_s": DEFAULT_WARMUP_S, "base_seed": BASE_SEED}})  # fmt: skip
    return out
