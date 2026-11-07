"""Live changes: demand, mix, signal policy, flyover close / reopen; log + exact replay."""

import hashlib

import numpy as np
import pytest

from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import DEMO_DEMAND, scaled
from trafficsim.engine.scenario import (
    OdFlow,
    Scenario,
    SetDemand,
    SetFlyover,
    SetMix,
    SetPolicy,
)
from trafficsim.engine.vehicle import CLASS_INDEX
from trafficsim.network.conflicts import conflict_table
from trafficsim.network.routing import grade_separated_roads

RUSH = scaled(DEMO_DEMAND, 1.5)


def _hash(sim: Simulation) -> str:
    vs = sim.vehicles
    h = hashlib.sha256()
    for a in (vs.vid, vs.seg, vs.s, vs.v, vs.route, vs.tail):
        h.update(np.ascontiguousarray(a).tobytes())
    h.update(str((sim.demand.generated, sim.exited, sim.demand.queued)).encode())
    return h.hexdigest()


def _run(net, changes=(), seconds=150.0, seed=3, **kw):
    sim = Simulation(net, Scenario(seed=seed, duration_s=seconds, demand=RUSH,
                                   changes=changes, **kw))  # fmt: skip
    hashes = []
    while sim.step():
        hashes.append(_hash(sim))
    return sim, hashes


# ------------------------------------------------------------------ log + replay -------
def test_replay_is_exact_for_a_short_run_with_every_kind_of_change(net):
    log = (
        (100, SetFlyover(False)),
        (150, SetDemand(scaled(DEMO_DEMAND, 0.5))),
        (200, SetMix((("car", 0.2), ("truck_bus", 0.3), ("two_wheeler", 0.4), ("cav", 0.1)))),
        (250, SetPolicy("max_pressure")),
        (300, SetFlyover(True)),
    )
    (a, ha), (_, hb) = _run(net, log, seconds=40.0), _run(net, log, seconds=40.0)
    assert ha == hb and len(a.change_log) == 5 and [t for t, _ in a.change_log] == [
        100, 150, 200, 250, 300,
    ]  # fmt: skip


@pytest.mark.slow
def test_same_seed_and_change_log_reproduce_the_run_exactly(net):
    log = (
        (300, SetFlyover(False)),
        (500, SetDemand(scaled(DEMO_DEMAND, 1.0))),
        (700, SetMix((("car", 0.2), ("truck_bus", 0.3), ("two_wheeler", 0.4), ("cav", 0.1)))),
        (900, SetFlyover(True)),
        (1100, SetPolicy("max_pressure")),
    )
    a, ha = _run(net, log)
    b, hb = _run(net, log)
    assert ha == hb and a.exited == b.exited and a.demand.generated > 150
    assert [(t, type(c).__name__) for t, c in a.change_log] == [
        (t, type(c).__name__) for t, c in log
    ]  # every change logged with the tick it was applied at
    print(f"\n[replay] {len(ha)} steps, {a.exited} exits, change log "
          f"{[(t, type(c).__name__) for t, c in a.change_log]}")  # fmt: skip


@pytest.mark.slow
def test_live_scheduling_equals_replaying_the_logged_scenario(net):
    live = Simulation(net, Scenario(seed=3, duration_s=150.0, demand=RUSH))
    hl = []
    while live.step():
        if live.tick == 400:
            live.schedule(SetFlyover(False))
        if live.tick == 900:
            live.schedule(SetPolicy("max_pressure_threshold"))
        hl.append(_hash(live))
    replay, hr = _run(net, tuple(live.change_log))
    assert live.change_log and hl == hr  # same seed + same log = same run


@pytest.mark.slow
def test_a_different_change_changes_the_run(net):
    _, h1 = _run(net, ((300, SetFlyover(False)),))
    _, h2 = _run(net)
    assert h1 != h2 and h1[:300] == h2[:300]  # identical until the change is applied


# ----------------------------------------------------------------- validation ----------
@pytest.mark.parametrize(
    "bad, text",
    [
        (lambda: SetMix((("car", 0.5), ("truck_bus", 0.47))), "sum to 1"),
        (lambda: SetMix((("car", 1.0), ("bus", 0.0))), "unknown vehicle classes"),
        (lambda: SetPolicy("uncontrolled"), "unknown signal policy"),
        (lambda: SetDemand((OdFlow("W", "E", -1.0),)), "non-negative"),
    ],
)
def test_invalid_changes_are_rejected_with_a_message_not_clamped(bad, text):
    with pytest.raises(ValueError, match=text):
        bad()


def test_changes_that_cannot_apply_are_rejected(net):
    sim = Simulation(net, Scenario(duration_s=20.0, demand=RUSH))
    with pytest.raises(ValueError, match="already open"):
        sim.schedule(SetFlyover(True))
    sim.schedule(SetFlyover(False))
    with pytest.raises(ValueError, match="already closed"):
        sim.schedule(SetFlyover(False))
    with pytest.raises(ValueError, match="unknown zone"):
        sim.schedule(SetDemand((OdFlow("W", "Nowhere", 10.0),)))
    sim.step_n(5)
    with pytest.raises(ValueError, match="past"):
        sim.schedule(SetMix(sim.current_mix), tick=2)
    free = Simulation(net, Scenario(duration_s=20.0, demand=RUSH, signal_control="uncontrolled"))
    with pytest.raises(ValueError, match="no signals"):
        free.schedule(SetPolicy("max_pressure"))


# ------------------------------------------------------------------ demand and mix -----
def test_mix_change_applies_to_vehicles_generated_afterwards(net):
    sim = Simulation(net, Scenario(seed=2, duration_s=120.0, demand=RUSH))
    sim.run_until(40.0)
    n0 = sim.demand.generated
    sim.schedule(SetMix((("car", 0.0), ("truck_bus", 1.0), ("two_wheeler", 0.0), ("cav", 0.0))))
    sim.run_until(120.0)
    vs = sim.vehicles
    later = {int(c) for c, t in zip(vs.cls, vs.t_gen, strict=True) if t > 40.0 + 1e-9}
    later |= {e.cls for e in sim.log.exits if e.t_gen > 40.0 + 1e-9}
    assert sim.demand.generated > n0 + 100 and later
    assert later == {CLASS_INDEX["truck_bus"]}


def test_demand_change_to_zero_stops_arrivals_and_back_restarts_them(net):
    sim = Simulation(net, Scenario(seed=2, duration_s=200.0, demand=RUSH))
    sim.run_until(50.0)
    sim.schedule(SetDemand(()))
    sim.run_until(51.0)
    g = sim.demand.generated
    sim.run_until(120.0)
    assert sim.demand.generated == g  # nothing arrives while the table is empty
    sim.schedule(SetDemand((OdFlow("W", "E", 1200.0),)))
    sim.run_until(200.0)
    assert 1200 / 3600 * 80 * 0.5 < sim.demand.generated - g < 1200 / 3600 * 80 * 1.5


# --------------------------------------------------------------- signal policy ---------
@pytest.mark.slow
@pytest.mark.parametrize("first, second", [("fixed_webster", "max_pressure"),
                                           ("max_pressure", "fixed_webster")])  # fmt: skip
def test_policy_switch_never_shows_conflicting_greens(net, first, second):
    sim = Simulation(net, Scenario(seed=4, duration_s=300.0, demand=RUSH, signal_control=first))
    table = conflict_table(net)
    names = []
    for k in range(3000):
        if k in (700, 1600, 2300):  # several switches at different phase moments
            sim.schedule(SetPolicy(second if k != 1600 else first))
        sim.step()
        ctrl = sim.signals[0]
        names.append(ctrl.name)
        ids = [sim.lg.ids[c] for ph in ctrl.phases for cid in ph.connector_ids
               if ctrl.allows(c := sim.lg.seg_of[cid])]  # fmt: skip
        assert not any(b in table[a] for a in ids for b in ids)
    assert {first, second} <= set(names) and sim.policy == second
    assert sim.box_stopped_vehicle_s == 0.0 and sim.emergency_brakings == 0


# --------------------------------------------------------------------- flyover --------
def _on_flyover(sim):
    fly = {sim.lg.seg_of[ln.id] for r in sim.network.roads
           if r.id in grade_separated_roads(sim.network) for ln in r.lanes}  # fmt: skip
    return {int(v) for v, s in zip(sim.vehicles.vid, sim.vehicles.seg, strict=True) if s in fly}


@pytest.mark.slow
def test_closed_from_the_start_nobody_uses_the_flyover(net):
    sim = Simulation(net, Scenario(seed=3, duration_s=120.0, demand=RUSH, flyover_open=False))
    for _ in range(1200):
        sim.step()
        assert not _on_flyover(sim)
    assert sim.demand.generated > 150


@pytest.mark.slow
def test_close_then_reopen_ramps_accept_nobody_new_while_closed(net):
    sim = Simulation(net, Scenario(seed=3, duration_s=240.0, demand=RUSH))
    sim.run_until(60.0)
    assert _on_flyover(sim)  # the flyover is in use
    before = _on_flyover(sim)
    sim.schedule(SetFlyover(False))
    entered = set()
    for _ in range(1200):  # 120 s closed
        sim.step()
        entered |= _on_flyover(sim) - before
    assert entered <= sim.grandfathered_vids  # only vehicles too close to turn round
    assert sim.rerouted > 10
    sim.run_until(180.0)
    sim.schedule(SetFlyover(True))
    used = set()
    for _ in range(600):
        sim.step()
        used |= _on_flyover(sim)
    print(f"\n[flyover] rerouted {sim.rerouted}, grandfathered {len(sim.grandfathered_vids)}, "
          f"used again after reopening: {len(used)}")  # fmt: skip
    assert used  # ramps accept vehicles again
    assert sim.emergency_brakings == 0 and sim.box_stopped_vehicle_s == 0.0
