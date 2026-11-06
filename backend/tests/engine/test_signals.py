"""J1 signals: ITE intergreens, measured saturation flow, Webster, max-pressure, safety."""

import numpy as np
import pytest

from tests.engine.test_lane_changes import DEMO_DEMAND
from trafficsim.engine.calibration import saturation_flows
from trafficsim.engine.constants import STEPS_PER_SECOND
from trafficsim.engine.loop import Simulation
from trafficsim.engine.params.control import (
    C_MAX_S,
    CLEARANCE_VEHICLE_LENGTH_M,
    G_MAX_S,
    G_MIN_S,
    ITE_DECEL_MPS2,
    PERCEPTION_REACTION_S,
)
from trafficsim.engine.scenario import DEFAULT_MIX, OdFlow, Scenario
from trafficsim.engine.webster import build_phases, webster_plan
from trafficsim.network.conflicts import conflict_table

J1_DEMAND = DEMO_DEMAND + (OdFlow("N1", "S1", 300), OdFlow("S1", "N1", 300))


def test_intergreens_follow_ite_formulas(net):
    j1 = next(j for j in net.junctions if j.id == "J1")
    for ph in build_phases(net, j1):
        v = net.road(ph.approach_road).speed_limit_mps
        width = (ph.all_red_s * v) - CLEARANCE_VEHICLE_LENGTH_M
        print(f"\n[intergreen] {ph.approach_road}: amber {ph.amber_s:.2f} s, all-red "
              f"{ph.all_red_s:.2f} s (box width {width:.1f} m at {v * 3.6:.0f} km/h)")  # fmt: skip
        assert ph.amber_s == pytest.approx(PERCEPTION_REACTION_S + v / (2 * ITE_DECEL_MPS2))
        assert width == pytest.approx(30.0 if ph.approach_road.startswith(("eb", "wb")) else 40.0)


def test_saturation_flow_is_measured_per_movement(net):
    sat = saturation_flows(net, DEFAULT_MIX, "J1")
    cars = saturation_flows(net, (("car", 1.0),), "J1")
    for cid in ("eb_surf_w:1>eb_surf_e:0", "n1_in:0>s1_out:0", "eb_surf_w:0>n1_out:0"):
        print(f"\n[saturation] {cid}: mixed {sat[cid]:.0f} veh/h, cars only {cars[cid]:.0f} veh/h")
    through = cars["eb_surf_w:1>eb_surf_e:0"]
    assert 1200 < through < 2100  # one lane of cars from a standing queue
    assert cars["eb_surf_w:0>n1_out:0"] < through  # tight left turn discharges slower


def test_webster_plan_numbers(net):
    sim = Simulation(net, Scenario(duration_s=60.0, demand=J1_DEMAND))
    plan = sim.signals[0].plan
    print(f"\n[webster] y {[round(y, 3) for y in plan.y]}, Y {plan.Y:.3f}, L {plan.lost_s:.1f} s, "
          f"C0 {plan.c0_s:.1f} s, C {plan.cycle_s:.1f} s, greens "
          f"{[round(g, 1) for g in plan.greens_s]} s")  # fmt: skip
    assert plan.c0_s == pytest.approx((1.5 * plan.lost_s + 5) / (1 - plan.Y))
    assert plan.cycle_s <= C_MAX_S + 1e-9 and min(plan.greens_s) >= G_MIN_S
    over = webster_plan(build_phases(net, net.junctions[0]),
                        {k: 5000.0 for k in sim.signals[0].phases[0].connector_ids} | {
                            c: 0.0 for ph in sim.signals[0].phases[1:] for c in ph.connector_ids},
                        saturation_flows(net, DEFAULT_MIX, "J1"), net)  # fmt: skip
    print(f"[webster] oversaturated case: Y {over.Y:.2f} -> C {over.cycle_s:.1f} s, flagged "
          f"{over.oversaturated}")  # fmt: skip
    assert over.oversaturated and over.cycle_s == pytest.approx(C_MAX_S)


@pytest.mark.parametrize("control", ["fixed_webster", "max_pressure"])
def test_signal_safety_and_timing(net, control):
    sim = Simulation(
        net, Scenario(seed=4, duration_s=900.0, demand=J1_DEMAND, signal_control=control)
    )
    ctrl = sim.signals[0]
    table = conflict_table(net)
    j1_conns = [sim.lg.seg_of[c] for ph in ctrl.phases for c in ph.connector_ids]
    for _ in range(9000):
        sim.step()
        green = [c for c in j1_conns if ctrl.allows(c)]
        ids = [sim.lg.ids[c] for c in green]
        assert not any(b in table[a] for a in ids for b in ids)  # never conflicting greens
        assert ctrl.state == "green" or not green
    h = ctrl.history
    dur = [(b[0] - a[0]) / STEPS_PER_SECOND for a, b in zip(h[:-1], h[1:], strict=True)]
    greens = [d for (t, p, st), d in zip(h[:-1], dur, strict=True) if st == "green"]
    ambers = {round(d, 1) for (t, p, st), d in zip(h[:-1], dur, strict=True) if st == "amber"}
    shares = np.bincount([p for t, p, st in h if st == "green"], minlength=len(ctrl.phases))
    print(f"\n[{control}] {len(greens)} greens: min {min(greens):.1f} s, max {max(greens):.1f} s, "
          f"mean {np.mean(greens):.1f} s; ambers {sorted(ambers)}; phase green counts "
          f"{shares.tolist()}; exited {sim.exited}, emergency {sim.emergency_brakings}, "
          f"box-held {sim.box_stopped_vehicle_s:.1f} veh-s")  # fmt: skip
    assert min(greens) >= G_MIN_S - 1e-9
    assert (
        max(greens)
        <= max(G_MAX_S, max(ctrl.plan.greens_s) if control == "fixed_webster" else 0) + 0.1
    )
    assert sim.emergency_brakings == 0 and sim.box_stopped_vehicle_s == 0.0
