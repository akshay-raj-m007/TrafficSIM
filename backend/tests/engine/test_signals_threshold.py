"""Thresholded max-pressure variant: derived switching threshold, hysteresis, safety.

The variant's parameters were fixed before any controller comparison: minimum green
G_MIN_THRESHOLD_S (15 s) and a switching threshold DERIVED from measured quantities
(capacity forfeited by one switch). The comparison below prints, but does not rank.
"""

import numpy as np
import pytest

from tests.engine.test_signals import J1_DEMAND
from trafficsim.engine.calibration import saturation_flows, startup_lost_times
from trafficsim.engine.constants import STEPS_PER_SECOND
from trafficsim.engine.loop import Simulation
from trafficsim.engine.params.control import G_MAX_S, G_MIN_S, G_MIN_THRESHOLD_S
from trafficsim.engine.scenario import DEFAULT_MIX, Scenario
from trafficsim.engine.signals import MaxPressure
from trafficsim.engine.webster import build_phases
from trafficsim.network.conflicts import conflict_table


def _controller(net, threshold, g_min_s):
    j1 = next(j for j in net.junctions if j.id == "J1")
    sim = Simulation(net, Scenario(duration_s=10.0, signal_control="uncontrolled"))
    phases = build_phases(net, j1)
    sat = {c: 1500.0 for ph in phases for c in ph.connector_ids}
    return MaxPressure("J1", phases, sim.lg, sat, g_min_s=g_min_s, threshold=threshold), sim


def _fake_pressures(ctrl, values):
    ctrl.pressures = lambda vs, lg: (np.array(values, dtype=float), np.ones(len(values)))


def test_hysteresis_requires_the_margin_and_the_minimum_green(net):
    thr = 1000.0
    ctrl, sim = _controller(net, thr, G_MIN_THRESHOLD_S)
    ctrl.elapsed = ctrl.g_min  # minimum green served
    _fake_pressures(ctrl, [500.0, 500.0 + thr - 1.0, 0.0, 0.0])
    assert ctrl._decide(sim.vehicles, sim.lg) is None  # advantage below the threshold
    _fake_pressures(ctrl, [500.0, 500.0 + thr + 1.0, 0.0, 0.0])
    assert ctrl._decide(sim.vehicles, sim.lg) == 1  # advantage above it
    ctrl.elapsed = ctrl.g_min - 1  # a tick short of the minimum green
    assert ctrl._decide(sim.vehicles, sim.lg) is None
    assert ctrl.g_min == G_MIN_THRESHOLD_S * STEPS_PER_SECOND


def test_pure_variant_is_unchanged_textbook_rule(net):
    ctrl, sim = _controller(net, 0.0, G_MIN_S)
    ctrl.elapsed = ctrl.g_min
    _fake_pressures(ctrl, [500.0, 500.1, 0.0, 0.0])
    assert ctrl._decide(sim.vehicles, sim.lg) == 1  # any positive advantage switches
    assert ctrl.g_min == G_MIN_S * STEPS_PER_SECOND


@pytest.mark.slow
def test_threshold_is_derived_from_measured_quantities(net):
    sim = Simulation(net, Scenario(duration_s=10.0, demand=J1_DEMAND,
                                   signal_control="max_pressure_threshold"))  # fmt: skip
    c = sim.signals[0]
    sat = saturation_flows(net, DEFAULT_MIX, "J1")
    l1 = startup_lost_times(net, DEFAULT_MIX, "J1")
    s_ref = np.mean(list(sat.values()))
    inter = np.mean([ph.intergreen_s for ph in c.phases])
    expected_lost = inter + np.mean(list(l1.values()))
    print(f"\n[threshold] mean intergreen {inter:.2f} s + mean measured start-up loss "
          f"{np.mean(list(l1.values())):.2f} s = {expected_lost:.2f} s lost per switch; "
          f"s_ref {s_ref:.0f} veh/h -> forfeited {expected_lost * s_ref / 3600:.2f} veh -> "
          f"threshold {c.threshold:.0f} (veh x veh/h); "
          f"min green {G_MIN_THRESHOLD_S} s")  # fmt: skip
    assert c.lost_per_switch_s == pytest.approx(expected_lost)
    assert c.threshold == pytest.approx(expected_lost * s_ref / 3600 * s_ref)
    assert min(l1.values()) > 0  # measured start-up loss is positive for every movement


@pytest.mark.slow
def test_three_controllers_are_safe_and_report_their_behaviour(net):
    table = {}
    table_conf = conflict_table(net)
    for control in ("fixed_webster", "max_pressure", "max_pressure_threshold"):
        sim = Simulation(net, Scenario(seed=4, duration_s=600.0, demand=J1_DEMAND,
                                       signal_control=control))  # fmt: skip
        ctrl = sim.signals[0]
        j1 = [sim.lg.seg_of[c] for ph in ctrl.phases for c in ph.connector_ids]
        for _ in range(6000):
            sim.step()
            ids = [sim.lg.ids[c] for c in j1 if ctrl.allows(c)]
            assert not any(b in table_conf[a] for a in ids for b in ids)
        h = ctrl.history
        greens = [(b[0] - a[0]) / STEPS_PER_SECOND
                  for a, b in zip(h[:-1], h[1:], strict=True) if a[2] == "green"]  # fmt: skip
        table[control] = (len(greens), float(np.mean(greens)), min(greens), max(greens),
                          sim.exited, sim.demand.queued, sim.emergency_brakings)  # fmt: skip
        assert sim.emergency_brakings == 0 and sim.box_stopped_vehicle_s == 0.0
    print("\n[controllers, seed 4, 600 s] greens / mean / min / max green (s) / exited / queued")
    for k, (n, m, lo, hi, ex, q, _) in table.items():
        print(f"   {k:24s} {n:3d} {m:6.1f} {lo:6.1f} {hi:6.1f} {ex:5d} {q:4d}")
    pure, thr = table["max_pressure"], table["max_pressure_threshold"]
    assert thr[2] >= G_MIN_THRESHOLD_S - 0.1  # never switches before the longer minimum
    assert thr[0] < pure[0]  # fewer switches than the textbook rule
    assert thr[3] <= G_MAX_S + 0.1
