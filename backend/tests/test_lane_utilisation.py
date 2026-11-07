"""Every lane open to traffic carries vehicles under the default demand (listed exceptions only).

The 144 structure tests prove that routes *exist*; this proves that vehicles *use* them. A lane
or connector with fewer than ``MIN_ARRIVALS_H`` arrivals per hour and an occupancy below
``MIN_OCCUPANCY`` fails unless ``engine/utilisation_exceptions.py`` lists it with a reason.
"""

import re
from functools import cache
from pathlib import Path

import pytest

from trafficsim.engine.presets import DEFAULT_DEMAND
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.utilisation import measure
from trafficsim.engine.utilisation_exceptions import EXCEPTIONS, explain
from trafficsim.network.demo import build_demo_network
from trafficsim.network.structure import Structure

README = Path(__file__).resolve().parents[2] / "README.md"
DURATION_S, WARMUP_S = 900.0, 300.0

CASES = {
    "default": (None, {}),
    "j2_one_lane": (1, {}),
    "narrow_1x2.5": (Structure(2, 1, 1, 2.5, 2.5), {}),
    "surface_3": (Structure(2, 3, 2, 3.5, 3.5), {}),
    "mixed_4_3": (Structure(2, 4, 3, 3.5, 3.5), {}),
    "wide_4x4.0": (Structure(2, 4, 4, 4.0, 4.0), {}),
    "flyover_closed": (None, {"flyover_open": False}),
}


@cache
def _run(name):
    structure, extra = CASES[name]
    net = build_demo_network() if structure is None else build_demo_network(structure)
    sc = Scenario(seed=1, duration_s=DURATION_S, demand=DEFAULT_DEMAND, **extra)
    return measure(net, sc, WARMUP_S), extra.get("flyover_open", True), net


@pytest.mark.slow  # each case simulates 900 s (about 20 s)
@pytest.mark.parametrize("name", list(CASES))
def test_every_open_lane_carries_vehicles_unless_listed(name):
    rows, flyover_open, net = _run(name)
    s = net.road("eb_surf_w").n_lanes
    empty = [r for r in rows if not r.used and explain(r.id, flyover_open, s) is None]
    for r in empty:
        print(f"[{name}] EMPTY {r.id}: cause {r.cause}, route demand {r.demand_h:.0f} veh/h")
    assert not empty, [r.id for r in empty]
    # a listed exception that is not actually empty is not an exception: keep the list honest
    # (connectors only: a middle lane may be used by lane-changing traffic and still be empty in
    # its far parts, so a lane in the list is allowed to be used; a connector is not)
    used_listed = [
        r.id for r in rows if r.used and r.road is None and explain(r.id, flyover_open, s)
    ]
    assert not used_listed, f"listed as exception but carrying traffic: {used_listed}"


@pytest.mark.slow
@pytest.mark.parametrize("name", ["default", "flyover_closed"])
def test_no_empty_lane_is_unexplained(name):
    """Every empty segment has a computed cause, and none is a lane-choice problem."""
    rows, _, _ = _run(name)
    assert [r.id for r in rows if r.cause == "unexplained"] == []


def test_every_exception_is_documented_in_the_readme():
    text = README.read_text(encoding="utf-8")
    assert "Lane utilisation" in text
    for e in EXCEPTIONS:
        assert re.search(rf"`{e.key}`", text), f"README does not list exception {e.key}"
