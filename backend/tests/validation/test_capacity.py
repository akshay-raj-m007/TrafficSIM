"""Validation: measured lane capacity.

1. Free-flow capacity from the ring-road fundamental diagram (cars): the maximum of
   flow = density x mean speed over homogeneous runs. Reference: single-lane capacities
   of roughly 1,800-2,400 veh/h for cars (HCM 6th ed. basic segments up to 2,400 pc/h/ln;
   urban arterials lower).
2. Queue-discharge (saturation) flow at J1's stop line, measured by releasing standing
   queues (engine/calibration.py). Reference: HCM base saturation flow 1,900 pc/h/ln;
   IRC:SP:41 gives 525 PCU/h per metre of approach width (~1,840 PCU/h for 3.5 m).
   Mixed traffic is reported in vehicles, not PCU, so it is lower by construction.
Queue discharge is below the steady-state maximum of the same desired speed because
vehicles cross the line while still accelerating (start-up transient, about 7 % at a
40 km/h desired speed); the 60 km/h free-flow maximum is higher mainly because of the
higher desired speed. This is NOT the motorway "capacity drop" (see README, "Known
differences from HCM"). All numbers are printed.
"""

import pytest

from tests.validation.ring import run_ring
from trafficsim.engine.calibration import saturation_flows
from trafficsim.engine.scenario import DEFAULT_MIX

FD_DENSITIES = (20, 30, 40, 50, 55, 60, 65)
FD_DURATION_S = 600.0
FREE_FLOW_CAPACITY_RANGE = (1800.0, 2400.0)
SATURATION_RANGE_CARS = (1500.0, 2000.0)


pytestmark = pytest.mark.slow  # long simulation runs


def test_free_flow_capacity_from_fundamental_diagram():
    rows = []
    for rho in FD_DENSITIES:
        sim, ts, xs, vs, L, v_eq = run_ring(rho, FD_DURATION_S)
        v = vs[ts >= FD_DURATION_S / 2]
        rows.append((rho, rho * v.mean() * 3.6, v.mean() * 3.6, (v < 0.5).mean()))
    print("\n[capacity] ring fundamental diagram (cars): veh/km -> flow veh/h (mean km/h, stopped)")
    for rho, q, vm, st in rows:
        print(f"   {rho:3d} -> {q:6.0f} ({vm:4.1f}, {st:.0%})")
    q_max = max(q for _, q, _, _ in rows)
    rho_c = next(rho for rho, q, _, _ in rows if q == q_max)
    print(f"[capacity] max lane flow {q_max:.0f} veh/h at {rho_c} veh/km")
    lo, hi = FREE_FLOW_CAPACITY_RANGE
    assert lo <= q_max <= hi


def test_stop_line_saturation_flow(net):
    cars = saturation_flows(net, (("car", 1.0),), "J1")
    mixed = saturation_flows(net, DEFAULT_MIX, "J1")
    through = ("eb_surf_w:1>eb_surf_e:0", "wb_surf_e:0>wb_surf_w:1", "n1_in:0>s1_out:0")
    print("\n[capacity] J1 saturation flow, veh/h per lane (cars only / default mix)")
    for c in through:
        print(f"   through {c:26s} {cars[c]:6.0f} / {mixed[c]:6.0f}")
    for kind in ("left", "right"):
        ids = [c.id for c in net.connectors if c.junction_id == "J1" and c.movement == kind]
        print(f"   {kind} turns (cars): {min(cars[c] for c in ids):.0f}-"
              f"{max(cars[c] for c in ids):.0f} (curvature-limited turn speeds)")  # fmt: skip
    lo, hi = SATURATION_RANGE_CARS
    for c in through:
        assert lo <= cars[c] <= hi
        assert mixed[c] < cars[c] * 1.05  # heavier mix discharges no faster (in vehicles)
