"""Physics on the demo network: trucks slow on the flyover upgrade; narrow lanes are slower.

The demo up-ramp is short (180 m, smoothstep profile, peak grade 5.4 % at mid-length).
At free flow a truck carries momentum over it, so the slowdown is modest; from a
standing start (e.g. leaving a queue at the ramp foot) the grade bites much harder. Both
are measured; nothing here is tuned to reach a target.
"""

import numpy as np

from tests.helpers import on_segments, straight_network, track
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import CLASS_INDEX

RAMP_FOOT_S = 545.0  # 5 m before the end of eb_w4 (550 m), where the up-ramp starts
RAMP_LEN_M = 180.0


def _free_flow_ramp(net, cls):
    sim = Simulation(net, Scenario(duration_s=600.0))
    vid = sim.place_vehicle("W", "E", cls, 3, 20.0, 0.0)  # median lane → up-ramp
    ramp = on_segments(track(sim, vid, 3000), "eb_ramp_up")
    return ramp.min(), sim.lg.v0_eff[sim.lg.seg_of["eb_ramp_up:1"], CLASS_INDEX[cls]]


def test_free_flow_slowdown_on_upgrade(net):
    res = {cls: _free_flow_ramp(net, cls) for cls in ("truck_bus", "car", "two_wheeler")}
    for cls, (vmin, v0) in res.items():
        print(f"\n[upgrade, free flow] {cls}: min {vmin * 3.6:.1f} km/h of desired "
              f"{v0 * 3.6:.1f} km/h ({vmin / v0:.1%})")  # fmt: skip
    truck_min, truck_v0 = res["truck_bus"]
    assert truck_min < 0.97 * truck_v0  # measurable slowdown from the grade
    for cls in ("car", "two_wheeler"):
        vmin, v0 = res[cls]
        assert vmin > 0.995 * v0  # enough power: no visible effect


def _speed_after(sim, vid, dist_m):
    """Speed after travelling dist_m along the path (lane changes keep s; transfers add
    the remainder of the segment left)."""
    lg = sim.lg
    i = sim.row_of(vid)
    seg, s_old = int(sim.vehicles.seg[i]), float(sim.vehicles.s[i])
    travelled = 0.0
    while travelled < dist_m:
        sim.step()
        i = sim.row_of(vid)
        new_seg, s_new = int(sim.vehicles.seg[i]), float(sim.vehicles.s[i])
        same_road = lg.road_of[new_seg] is not None and lg.road_of[new_seg] == lg.road_of[seg]
        if new_seg == seg or same_road:
            travelled += s_new - s_old
        else:
            travelled += float(lg.length[seg]) - s_old + s_new
        seg, s_old = new_seg, s_new
    return float(sim.vehicles.v[i])


def test_standing_start_up_the_ramp_vs_flat(net):
    up = Simulation(net, Scenario(duration_s=600.0))
    v_up = _speed_after(
        up, up.place_vehicle("W", "E", "truck_bus", 3, RAMP_FOOT_S, 0.0), RAMP_LEN_M
    )
    flat = Simulation(straight_network(length_m=1000.0, speed_kmh=50.0), Scenario(duration_s=600.0))
    v_flat = _speed_after(flat, flat.place_vehicle("A", "B", "truck_bus", 0, 20.0, 0.0), RAMP_LEN_M)
    ratio = v_up / v_flat
    print(f"\n[upgrade, standing start] truck after {RAMP_LEN_M:.0f} m: up-ramp "
          f"{v_up * 3.6:.1f} km/h vs flat {v_flat * 3.6:.1f} km/h ({ratio:.1%})")  # fmt: skip
    assert 0.5 * v_flat < v_up < 0.9 * v_flat  # two-sided: catches measurement errors too


def test_narrow_lane_lowers_free_speed(net):
    sim = Simulation(net, Scenario(duration_s=600.0))
    vid = sim.place_vehicle("N2", "E", "car", 0, 10.0, 0.0)
    v = on_segments(track(sim, vid, 800), "n2_in")
    k = sim.lg.seg_of["n2_in:0"]
    lim, v0 = sim.lg.vlimit[k] * 3.6, sim.lg.v0_eff[k, 0] * 3.6
    print(f"\n[lane width] car on 2.75 m lane (limit {lim:.0f} km/h): "
          f"max {v.max() * 3.6:.2f} km/h, model v0_eff {v0:.2f} km/h")  # fmt: skip
    assert np.isclose(v.max(), sim.lg.v0_eff[k, 0], rtol=0.01)
    assert v.max() < sim.lg.vlimit[k]
