"""The built-in experiments: precomputed, shipped with the app, served instantly.

    policy_rush    Webster vs pure max-pressure vs thresholded max-pressure, rush hour
    flyover_rush   flyover open vs closed (from the start), rush hour
    surface_closed surface road 3 lanes x 3.5 m vs 2 lanes x 2.75 m, flyover closed, rush hour
    flyover_width  flyover group 2 lanes x 3.5 m vs 2 lanes x 2.75 m, flyover open, rush hour
    flyover_lanes  flyover group 2 lanes vs 1 lane (3.5 m), flyover open, rush hour

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

from trafficsim.engine.presets import RUSH_SCALE
from trafficsim.engine.runmetrics import METRICS_VERSION
from trafficsim.engine.sourcedigest import source_digest
from trafficsim.network.structure import Structure
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


def _surface(name: str, lanes: int, width_m: float) -> dict:
    """Rush hour with the flyover closed (the surface carries all through traffic)."""
    doc = _rush(name, flyover_open=False)
    doc["structure"] |= {"surface_lanes": lanes, "surface_width_m": width_m}
    return doc


def _flyover(name: str, lanes: int, width_m: float) -> dict:
    """Rush hour, flyover open, flyover group of the given size (surface road unchanged)."""
    doc = _rush(name)
    doc["structure"] |= {"flyover_lanes": lanes, "flyover_width_m": width_m}
    return doc


def definitions() -> dict[str, dict]:
    webster = _rush("Webster", policy="fixed_webster")
    mp = _rush("Max-pressure", policy="max_pressure")
    mpt = _rush("Thresholded max-pressure", policy="max_pressure_threshold")
    return {
        "policy_rush": {
            "title": "Signal policy at rush hour",
            "description": "Webster (fixed-time) against pure max-pressure and thresholded "
            f"max-pressure at J1, rush-hour demand (every flow x{RUSH_SCALE}). Difference = B - A.",
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
        "surface_closed": {
            "title": "Surface lanes with the flyover closed, rush hour",
            "description": "Surface road 3 lanes x 3.5 m (A) against 2 lanes x 2.75 m (B), flyover "
            "closed from the start, so the surface carries all through traffic. Rush-hour demand. "
            "Difference = B - A.",
            "comparisons": [
                (
                    "Surface 3 x 3.5 m vs 2 x 2.75 m, flyover closed",
                    _surface("Surface 3 lanes x 3.5 m", 3, 3.5),
                    _surface("Surface 2 lanes x 2.75 m", 2, 2.75),
                )
            ],  # fmt: skip
        },
        "flyover_width": {
            "title": "Flyover width alone at rush hour",
            "description": "Flyover group 2 lanes x 3.5 m (A) against 2 lanes x 2.75 m (B), "
            "flyover open, rush-hour demand: the width alone, same lane count. Difference = B - A.",
            "comparisons": [
                (
                    "Flyover 2 x 3.5 m vs 2 x 2.75 m",
                    _flyover("Flyover 2 lanes x 3.5 m", 2, 3.5),
                    _flyover("Flyover 2 lanes x 2.75 m", 2, 2.75),
                )
            ],  # fmt: skip
        },
        "flyover_lanes": {
            "title": "Flyover lane count at rush hour",
            "description": "Flyover group 2 lanes (A) against 1 lane (B), both 3.5 m, flyover "
            "open, rush-hour demand. Difference = B - A.",
            "comparisons": [
                (
                    "Flyover 2 lanes vs 1 lane",
                    _flyover("Flyover 2 lanes", 2, 3.5),
                    _flyover("Flyover 1 lane", 1, 3.5),
                )
            ],  # fmt: skip
        },
    }


def request_for(a: dict, b: dict) -> dict:
    return {"a": deepcopy(a), "b": deepcopy(b), "runs": RUNS, "duration_s": DEFAULT_DURATION_S,
            "warmup_s": DEFAULT_WARMUP_S, "base_seed": BASE_SEED}  # fmt: skip


def current_stamp() -> dict:
    return {
        "model_digest": model_digest(Structure()),
        "metrics_version": METRICS_VERSION,
        "source_digest": source_digest(),
    }


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
