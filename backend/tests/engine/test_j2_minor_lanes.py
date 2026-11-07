"""J2 minor approach: a left-turn lane and a right-turn lane (flared approach).

Why: with ONE shared lane a waiting right-turner, which must cross the whole major road,
blocked the left-turners behind it although the left turn's gap was open 37 % of the time
(see README, "Give-way junction"). These tests prove the change is contained to J2's minor
approach and does what it should. ``build_demo_network(1)`` is the original single-lane
network, kept so the comparison is exact.
"""

import numpy as np
import pytest

from trafficsim.engine.loop import Simulation
from trafficsim.engine.params.control import (
    CRITICAL_GAP_MINOR_RIGHT_S,
    FOLLOW_UP_MINOR_RIGHT_S,
)
from trafficsim.engine.presets import DEMO_DEMAND
from trafficsim.engine.scenario import OdFlow, Scenario
from trafficsim.network.conflicts import conflict_table
from trafficsim.network.demo import build_demo_network

OLD = build_demo_network(1)
OTHER_DEMAND = tuple(f for f in DEMO_DEMAND if f.origin != "N2")  # nothing enters from N2


# ------------------------------------------------------------------ structure -----------
def test_only_the_minor_approach_changed(net):
    assert net is not OLD
    old = {c.id: c for c in OLD.connectors}
    for c in net.connectors:
        if c.from_lane.startswith("n2_in"):
            continue
        o = old[c.id]
        assert np.array_equal(c.path, o.path) and c.length_m == o.length_m
        assert (c.yields, c.movement, c.junction_id) == (o.yields, o.movement, o.junction_id)
    assert {c.id for c in OLD.connectors if not c.from_lane.startswith("n2_in")} == {
        c.id for c in net.connectors if not c.from_lane.startswith("n2_in")
    }
    for r in OLD.roads:
        if r.id != "n2_in":
            n = net.road(r.id)
            assert [ln.id for ln in n.lanes] == [ln.id for ln in r.lanes]
            for a, b in zip(n.lanes, r.lanes, strict=True):
                assert np.array_equal(a.centreline, b.centreline) and a.width_m == b.width_m


def test_each_turn_has_its_own_lane_and_the_two_do_not_conflict(net):
    assert net.road("n2_in").n_lanes == 2 and OLD.road("n2_in").n_lanes == 1
    ids = {c.id: c for c in net.connectors if c.from_lane.startswith("n2_in")}
    assert set(ids) == {"n2_in:0>eb_out:0", "n2_in:1>wb_e2:1"}
    assert ids["n2_in:0>eb_out:0"].movement == "left" and ids["n2_in:1>wb_e2:1"].movement == "right"
    t = conflict_table(net)
    assert "n2_in:1>wb_e2:1" not in t["n2_in:0>eb_out:0"]  # the minor turns share no conflict
    assert set(t["n2_in:0>eb_out:0"]) == {"eb_e2:0>eb_out:0"}  # left only merges with EB lane 0
    assert {"eb_e2:0>eb_out:0", "eb_e2:1>eb_out:1", "wb_in:1>wb_e2:1"} <= set(
        t["n2_in:1>wb_e2:1"]
    )  # right still crosses both EB lanes and merges into WB lane 1 (unchanged conflicts)


def test_single_lane_variant_reproduces_the_original(net):
    ids = {c.id for c in OLD.connectors if c.from_lane.startswith("n2_in")}
    assert ids == {"n2_in:0>eb_out:0", "n2_in:0>wb_e2:1"}  # both turns from lane 0
    assert OLD.road("n2_in").lanes[0].length_m == pytest.approx(388.0)
    with pytest.raises(ValueError):
        build_demo_network(3)


# ------------------------------------------------------- nothing else moves --------------
@pytest.mark.slow
@pytest.mark.parametrize("control", ["uncontrolled", "fixed_webster"])
def test_everything_else_is_bit_identical_when_nobody_uses_n2(control):
    """Same seed and demand without N2-origin traffic: every vehicle leaves at exactly the
    same time on both networks (J1 signals, flyover, lane drop, J2 major road, turns into N2)."""
    runs = []
    for variant in (1, 2):
        sim = Simulation(
            build_demo_network(variant),
            Scenario(seed=7, duration_s=300.0, demand=OTHER_DEMAND, signal_control=control),
        )
        sim.run_until(300.0)
        runs.append(sim)
    a, b = runs
    key = lambda s: [(e.vid, e.cls, e.route, e.t_gen, e.t_ins, e.t_exit) for e in s.log.exits]  # noqa: E731
    print(f"\n[isolation:{control}] {a.exited} exits identical on both networks: "
          f"{key(a) == key(b)}; lane changes {a.lane_changes} vs {b.lane_changes}; "
          f"junction entries {len(a.log.junction_entries)} vs "
          f"{len(b.log.junction_entries)}")  # fmt: skip
    assert a.exited > 50 and key(a) == key(b)
    assert a.lane_changes == b.lane_changes
    assert [(e.vid, e.t) for e in a.log.junction_entries] == [
        (e.vid, e.t) for e in b.log.junction_entries
    ]
    assert a.emergency_brakings == b.emergency_brakings == 0


# ------------------------------------------------------------ what it fixes -------------
def _entries(sim, conn: str) -> int:
    return sum(1 for e in sim.log.junction_entries if sim.lg.ids[e.conn] == conn)


def _run(variant: int, extra: tuple[OdFlow, ...], seconds=600.0, seed=11):
    base = (OdFlow("W", "E", 900.0), OdFlow("E", "W", 700.0), OdFlow("N2", "E", 150.0))
    sim = Simulation(
        build_demo_network(variant),
        Scenario(seed=seed, duration_s=seconds, demand=base + extra, signal_control="uncontrolled"),
    )
    sim.run_until(seconds)
    return sim


POOLED_SEEDS = range(11, 21)


@pytest.mark.slow
def test_left_turns_are_not_blocked_by_waiting_right_turns():
    """Pooled over 10 seeds: one seed serves only about 22 left-turners in 600 s (Poisson
    spread about 5), so the ratio of a single seed swings between 0.5 and 1.4 and cannot test
    the 0.8 threshold; the pooled ratio (0.88 with both keep-left biases) can."""
    saturated_right = (OdFlow("N2", "W", 600.0),)
    conn = "n2_in:0>eb_out:0"
    solo = sum(_entries(_run(2, (), seed=k), conn) for k in POOLED_SEEDS)
    flared = sum(_entries(_run(2, saturated_right, seed=k), conn) for k in POOLED_SEEDS)
    shared = _entries(_run(1, saturated_right), conn)  # seed 11 only: the starvation is large
    solo_11 = _entries(_run(2, ()), conn)
    print(
        f"\n[J2 left turns served in 600 s, {len(POOLED_SEEDS)} seeds pooled] left-only demand: "
        f"{solo}; with a saturated right turn: flared approach {flared}; seed 11 alone: "
        f"left-only {solo_11}, old shared lane {shared}"
    )
    assert flared >= 0.8 * solo  # the right-turn queue no longer starves the left turn
    assert shared < 0.5 * solo_11  # (the original behaviour, for the record)


@pytest.mark.slow
def test_right_turn_against_hcm_and_gap_acceptance():
    """The crossing movement had never been validated against HCM. Saturated right turn."""
    sim = _run(2, (OdFlow("N2", "W", 900.0),), seconds=900.0)
    lg, t = sim.lg, 900.0
    flow = lambda cid: _entries(sim, cid) / t * 3600  # noqa: E731
    vc = (flow("eb_e2:0>eb_out:0") + flow("eb_e2:1>eb_out:1")
          + flow("wb_in:1>wb_e2:1") + flow("wb_in:1>n2_out:0"))  # fmt: skip
    tc, tf = CRITICAL_GAP_MINOR_RIGHT_S[2], FOLLOW_UP_MINOR_RIGHT_S
    hcm = vc * np.exp(-vc * tc / 3600) / (1 - np.exp(-vc * tf / 3600))
    served = flow("n2_in:1>wb_e2:1")
    c = lg.seg_of["n2_in:1>wb_e2:1"]
    gaps = np.array([g for _, cc, g in sim.gates.accepted_gaps if cc == c])
    print(f"\n[J2 right turn] conflicting flow {vc:.0f} veh/h -> HCM capacity {hcm:.0f} veh/h; "
          f"simulation served {served:.0f} veh/h ({served / hcm:.0%} of HCM); accepted gaps "
          f"min {gaps.min():.2f} s (t_c {tc} s)")  # fmt: skip
    assert served > 0 and gaps.min() >= tc  # never accepts a gap below the critical gap
    assert sim.emergency_brakings == 0 and sim.box_stopped_vehicle_s == 0.0
