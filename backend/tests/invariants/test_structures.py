"""The hard invariants hold for every allowed structure (lane counts and widths).

The same per-step harness as the other invariant tests (independent collision check, conflict
points, conservation) plus spillback entries and the grade-separation transition check. Extremes
are tested explicitly: 1 lane per group at the narrowest width and 4 lanes per group at the widest.
"""

import math

import pytest

from tests.invariants.harness import run_checked
from trafficsim.engine.presets import DEFAULT_DEMAND
from trafficsim.engine.scenario import Scenario
from trafficsim.network.demo import build_demo_network
from trafficsim.network.structure import Structure

pytestmark = pytest.mark.slow  # each combination is a checked simulation (+ one calibration)

NARROW = Structure(2, 1, 1, 2.5, 2.5)  # 1 lane per group, narrowest
WIDE = Structure(2, 4, 4, 4.0, 4.0)  # 4 lanes per group, widest
MIXED = [
    Structure(2, 1, 4, 2.5, 4.0), Structure(2, 4, 1, 4.0, 2.5), Structure(1, 3, 2, 3.5, 3.0),
    Structure(2, 2, 3, 2.75, 3.5), Structure(2, 3, 3, 3.5, 2.75), Structure(2, 1, 2, 3.5, 3.5),
]  # fmt: skip


def _check(st: Structure, seconds: float = 180.0, scale: float = 1.0, seed: int = 8) -> None:
    from trafficsim.engine.presets import scaled

    net = build_demo_network(st)
    demand = scaled(DEFAULT_DEMAND, scale)
    steps = int(seconds * 10)
    rep = run_checked(net, Scenario(seed=seed, duration_s=seconds, demand=demand), steps)
    sim = rep.sim
    entries = sim.log.junction_entries
    short = [e for e in entries if not e.room >= e.need]
    unknown = [e for e in entries if math.isnan(e.room)]
    flyover = {sim.lg.seg_of[ln.id] for r in net.roads if r.kind in ("flyover", "ramp")
               for ln in r.lanes}  # fmt: skip
    ground_to_deck = [
        (a, b) for a, b in rep.transitions
        if (a in flyover) != (b in flyover) and sim.lg.road_of[b if b in flyover else a]
        not in {r.id for r in net.roads if r.kind == "ramp"}
    ]  # fmt: skip
    print(f"\n[structure S{st.surface_lanes}F{st.flyover_lanes} {st.surface_width_m}/"
          f"{st.flyover_width_m} m] peak {rep.peak_vehicles} veh, min gap {rep.min_gap:.2f} m, "
          f"overlaps {len(rep.conflict_overlaps)}, entries {len(entries)}, exited {sim.exited}, "
          f"emergency {sim.emergency_brakings}, box-held {sim.box_stopped_vehicle_s}")  # fmt: skip
    assert rep.min_gap > 0.0 and rep.min_speed >= 0.0  # no collision, no negative speed
    assert not rep.conflict_overlaps  # no two vehicles on conflicting paths at once
    assert not rep.conservation_errors  # spawned = active + exited + queued
    assert entries and not short and not unknown  # every entry had room at commitment
    assert sim.box_stopped_vehicle_s == 0.0 and sim.emergency_brakings == 0
    assert not ground_to_deck  # level changes happen only on the ramps
    assert sim.exited > 0


@pytest.mark.parametrize("st", [NARROW, WIDE], ids=["1-lane-2.5m", "4-lanes-4.0m"])
def test_the_extremes_hold_every_invariant(st):
    _check(st, seconds=240.0, scale=1.2)


def test_the_default_structure_is_unchanged_under_the_same_checks():
    _check(Structure(), seconds=180.0)


@pytest.mark.parametrize(
    "st",
    MIXED,
    ids=lambda s: (
        f"S{s.surface_lanes}F{s.flyover_lanes}-"
        f"{s.surface_width_m}-{s.flyover_width_m}-J{s.j2_minor_lanes}"
    ),
)
def test_mixed_combinations_hold_every_invariant(st):
    _check(st)
