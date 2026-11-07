"""Named scenario presets (raw scenario documents, validated like any imported JSON)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Final

from trafficsim.engine.presets import DEFAULT_DEMAND, RUSH_SCALE, scaled
from trafficsim.engine.scenario import DEFAULT_MIX
from trafficsim.network.structure import Structure
from trafficsim.server.scenario_doc import SCHEMA_VERSION, mix_of, rows_of
from trafficsim.server.session_config import DEFAULT_SIGNAL, SESSION_DURATION_S

DEFAULT_SEED: Final[int] = 42


def _doc(
    name: str, demand, *, structure: Structure | None = None, flyover_open: bool = True
) -> dict:
    return {
        "version": SCHEMA_VERSION,
        "name": name,
        "seed": DEFAULT_SEED,
        "duration_s": SESSION_DURATION_S,
        "structure": asdict(structure or Structure()),
        "initial": {
            "demand": rows_of(demand),
            "mix": mix_of(DEFAULT_MIX),
            "policy": DEFAULT_SIGNAL,
            "flyover_open": flyover_open,
        },
        "changes": [],
    }


PRESET_INFO: Final[dict[str, str]] = {
    "default": "Default demand (J2 minor road from measured capacities), flyover open.",
    "rush_hour": f"Every flow x{RUSH_SCALE}: J1 critical flow ratio 0.85 instead of 0.65.",
    "flyover_closed": "Default demand with the flyover closed from the start.",
    "j2_before": "Default demand, J2 minor road as ONE shared lane (the old layout).",
}


def preset(name: str) -> dict:
    """A fresh copy of a preset document."""
    builders = {
        "default": lambda: _doc("Default", DEFAULT_DEMAND),
        "rush_hour": lambda: _doc("Rush hour", scaled(DEFAULT_DEMAND, RUSH_SCALE)),
        "flyover_closed": lambda: _doc("Flyover closed", DEFAULT_DEMAND, flyover_open=False),
        "j2_before": lambda: _doc(
            "J2 before: one shared lane", DEFAULT_DEMAND, structure=Structure(j2_minor_lanes=1)
        ),
    }
    if name not in builders:
        raise KeyError(f"unknown preset {name!r}; known: {sorted(builders)}")
    return deepcopy(builders[name]())


def all_presets() -> dict[str, dict]:
    return {n: preset(n) for n in PRESET_INFO}
