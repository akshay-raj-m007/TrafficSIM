"""Vehicle poses (position, heading, pitch) follow the real lane and ramp geometry."""

import numpy as np
import pytest

from tests.helpers import straight_network
from trafficsim.engine.loop import Simulation
from trafficsim.engine.pose import PoseTable
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import CLASS_INDEX, LEN

V_MAX_MPS = 17.0  # fastest desired speed of any class (flyover limit 60 km/h)


def test_pose_is_the_centre_of_the_vehicle_on_its_lane():
    net = straight_network(length_m=1000.0, lanes=2, width_m=3.5)
    sim = Simulation(net, Scenario(duration_s=10.0))
    sim.place_vehicle("A", "B", "truck_bus", 1, 300.0, 0.0)  # lane 1: median side
    table = PoseTable(net, sim.lg)
    x, y, z, h, p = table.vehicle_poses(sim.vehicles)
    lane = net.lane("main:1")
    assert x[0] == pytest.approx(300.0 - LEN[CLASS_INDEX["truck_bus"]] / 2)  # centre, not front
    assert y[0] == pytest.approx(lane.centreline[0, 1])
    assert (z[0], h[0], p[0]) == (0.0, 0.0, 0.0)


def test_pose_follows_ramp_elevation_and_pitch(net):
    sim = Simulation(net, Scenario(duration_s=10.0))
    table = PoseTable(net, sim.lg)
    seg = np.array([sim.lg.seg_of["eb_ramp_up:0"]] * 3)
    s = np.array([0.0, 0.5, 1.0]) * sim.lg.length[seg[0]]
    x, y, z, h, p = table.at(seg, s)
    deck = net.meta["deck_z_m"]
    ramp_len = float(sim.lg.length[seg[0]])
    # smoothstep profile: z(mid) = deck/2, peak grade 1.5 * deck / plan length at mid-length
    assert z[0] == pytest.approx(0.0, abs=1e-6) and z[2] == pytest.approx(deck, abs=1e-6)
    assert z[1] == pytest.approx(deck / 2, abs=0.02)
    assert np.tan(p[1]) == pytest.approx(1.5 * deck / ramp_len, rel=0.03)
    assert p[0] >= 0 and abs(h[1]) < 0.01  # climbing, heading east


def test_headings_distinguish_the_two_directions(net):
    sim = Simulation(net, Scenario(duration_s=10.0))
    table = PoseTable(net, sim.lg)
    eb, wb = sim.lg.seg_of["eb_w4:0"], sim.lg.seg_of["wb_w4:0"]
    _, _, _, h, _ = table.at(np.array([eb, wb]), np.array([100.0, 100.0]))
    assert h[0] == pytest.approx(0.0, abs=1e-9)
    assert abs(h[1]) == pytest.approx(np.pi, abs=1e-9)


@pytest.mark.slow
def test_pose_is_continuous_along_a_whole_route(net):
    """No jumps across segment transfers, ramps, the flyover and the J2 turn box."""
    sim = Simulation(net, Scenario(duration_s=400.0, signal_control="uncontrolled"))
    vid = sim.place_vehicle("W", "E", "truck_bus", 3, 20.0, 0.0)
    table = PoseTable(net, sim.lg)
    prev, worst, pitch_max, z_max, steps = None, 0.0, 0.0, 0.0, 0
    n_lc = 0
    while sim.row_of(vid) is not None:
        i = sim.row_of(vid)
        x, y, z, h, p = (a[i] for a in table.vehicle_poses(sim.vehicles))
        lc = len(sim.log.lane_changes)
        if prev is not None and lc == n_lc:  # lane changes jump a lane width by design
            worst = max(worst, float(np.hypot(x - prev[0], y - prev[1])))
        prev, n_lc, steps = (x, y), lc, steps + 1
        pitch_max, z_max = max(pitch_max, float(p)), max(z_max, float(z))
        sim.step()
    print(f"\n[pose] {steps} steps, max per-step displacement {worst:.3f} m "
          f"(v_max*dt = {V_MAX_MPS * 0.1:.2f} m), max pitch {np.degrees(pitch_max):.2f} deg, "
          f"max z {z_max:.3f} m")  # fmt: skip
    assert 0.0 < worst <= V_MAX_MPS * sim.dt + 1e-6
    assert z_max == pytest.approx(net.meta["deck_z_m"], abs=0.01)  # reaches the deck
    assert 0.03 < pitch_max < 0.06  # ~5.4 % peak grade on the up-ramp
