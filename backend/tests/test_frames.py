"""Binary frame codec (v2: lane-graph placement): round trip, golden file, brake, blending."""

import json

import numpy as np
import pytest

from tools.gen_golden_frame import FIXTURE_DIR, FMT, golden
from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import DEMO_DEMAND
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import LEN
from trafficsim.network.demo import build_demo_network
from trafficsim.server.frames import (
    BRAKE_LIGHT_DECEL_MPS2,
    BYTES_PER_VEHICLE,
    HEADER,
    LC_BLEND_S,
    FrameEncoder,
    format_for,
    pack_frame,
    segment_table,
    unpack_frame,
    world_pose,
)


def test_frame_size_is_12_plus_9_per_vehicle():
    rng = np.random.default_rng(0)
    for n in (0, 1, 200, 600):
        a = rng.random(n)
        data = pack_frame(
            FMT, phase=0, state=0, epoch=0, tick=5, speed_index=3, vid=np.arange(n),
            seg=np.zeros(n, int), s=a * 100, lat=a * 0, speed=a * 10, brake=a > 0.5,
            cls=np.zeros(n, int),
        )  # fmt: skip
        assert len(data) == HEADER.size + BYTES_PER_VEHICLE * n == 12 + 9 * n


def test_round_trip_is_within_the_quantisation_steps():
    rng = np.random.default_rng(1)
    n = 500
    seg, s = rng.integers(0, 120, n), rng.uniform(0, 550, n)
    lat, v = rng.uniform(-3.5, 3.5, n), rng.uniform(0, 17, n)
    brake, cls = rng.random(n) > 0.5, rng.integers(0, 4, n)
    data = pack_frame(FMT, phase=1, state=2, epoch=9, tick=77, speed_index=4, vid=np.arange(n),
                      seg=seg, s=s, lat=lat, speed=v, brake=brake, cls=cls)  # fmt: skip
    d = unpack_frame(FMT, data)
    assert (d["phase"], d["state"], d["epoch"], d["tick"], d["n"], d["speed_index"]) == (
        1, 2, 9, 77, n, 4,
    )  # fmt: skip
    assert (d["seg"] == seg).all()
    assert np.abs(d["s"] - s).max() <= FMT.s_scale_m / 2 + 1e-9
    assert np.abs(d["lat"] - lat).max() <= FMT.lat_scale_m / 2 + 1e-9
    assert np.abs(d["speed"] - v).max() <= 0.05 + 1e-9
    assert (d["brake"] == brake).all() and (d["cls"] == cls).all()


def test_malformed_frames_are_rejected():
    data, _ = golden()
    with pytest.raises(ValueError):
        unpack_frame(FMT, data[:-1])
    with pytest.raises(ValueError):
        unpack_frame(FMT, b"\x01" + data[1:])


def test_golden_frame_files_are_current():
    """The fixtures the TypeScript decoder tests read must equal what the encoder writes."""
    data, expected = golden()
    assert (FIXTURE_DIR / "golden_frame.bin").read_bytes() == data, (
        "run `python tools/gen_golden_frame.py` in backend/ and commit the fixtures"
    )
    doc = json.loads((FIXTURE_DIR / "golden_frame.json").read_text(encoding="utf-8"))
    assert doc == {"format": FMT.to_dict(), "expected": expected}
    assert expected["vehicles"]["id"] == [3, 1, 40000, 12, 999]  # 65537 wraps to 1


def _sim(seed=5, seconds=0.0):
    sim = Simulation(
        build_demo_network(),
        Scenario(seed=seed, duration_s=600.0, demand=DEMO_DEMAND, signal_control="uncontrolled"),
    )
    sim.run_until(seconds)
    return sim


@pytest.mark.slow
def test_encoder_matches_engine_state_and_brake_convention():
    sim = _sim(seconds=400.0)  # queues have formed (J2 minor road, lane-drop merge)
    enc = FrameEncoder(sim)
    d = unpack_frame(enc.fmt, enc.encode(epoch=0, speed_index=3))
    vs = sim.vehicles
    x, y, z, h, p = enc.pose.vehicle_poses(vs)
    X, Y, Z, H, P = world_pose(enc.pose, d)  # what the browser computes from the frame
    assert d["n"] == vs.n > 100 and (d["id"] == (vs.vid & 0xFFFF)).all()
    dev = np.hypot(X - x, Y - y)
    blending = {e.vid & 0xFFFF for e in sim.log.lane_changes if sim.time_s - e.t < LC_BLEND_S}
    quiet = ~np.isin(d["id"], list(blending))
    assert dev[quiet].max() <= 0.05  # 1 cm arc + 2.5 cm lateral quantisation, nobody else off
    assert dev.max() <= 3.5 + 0.05  # a blend never offsets more than one lane width
    assert np.abs(Z - z).max() < 0.05
    assert (d["cls"] == vs.cls).all() and d["tick"] == sim.tick
    hard = vs.acc <= -BRAKE_LIGHT_DECEL_MPS2
    assert d["brake"][hard].all()  # every hard-braking vehicle shows its brake lights
    assert not d["brake"][(vs.acc > 0.5) & (vs.v > 1.0)].any()  # accelerating, moving: none
    standing = (vs.v < 0.1) & (vs.acc < 0.1)
    assert standing.sum() > 0 and d["brake"][standing].all()  # standing queue: lights on
    print(f"\n[frame] {vs.n} vehicles, {int(d['brake'].sum())} braking, "
          f"max pose error {dev[quiet].max() * 100:.1f} cm")  # fmt: skip


def test_lane_change_is_blended_laterally_not_a_jump():
    sim = _sim(seed=7)
    enc = FrameEncoder(sim)
    for _ in range(3000):
        sim.step()
        if sim.log.lane_changes:
            break
    ev = sim.log.lane_changes[0]
    row = int(np.flatnonzero(sim.vehicles.vid == ev.vid)[0])

    def encoded_xy():
        d = unpack_frame(enc.fmt, enc.encode(0, 3))
        X, Y, *_ = world_pose(enc.pose, d)
        k = int(np.flatnonzero(d["id"] == (ev.vid & 0xFFFF))[0])
        return np.array([X[k], Y[k]])

    # The event is logged before that step's movement: the old lane at the vehicle's
    # *current* position is where the blended frame must start.
    half = LEN[sim.vehicles.cls[row]] / 2
    x, y, *_ = enc.pose.at(np.array([ev.from_seg]), np.array([sim.vehicles.s[row] - half]))
    old = np.array([x[0], y[0]])
    start = encoded_xy()
    lateral = []
    for _ in range(int(LC_BLEND_S * 10) + 2):
        sim.step()
        if sim.row_of(ev.vid) is None:
            break
        i = sim.row_of(ev.vid)
        cx, cy, *_ = enc.pose.vehicle_poses(sim.vehicles)
        enc_xy = encoded_xy()
        lateral.append(float(np.hypot(enc_xy[0] - cx[i], enc_xy[1] - cy[i])))
    print(f"\n[blend] first lane change at t={ev.t:.1f} s: start offset from old lane "
          f"{np.linalg.norm(start - old):.3f} m; lateral offset to true pose over the blend: "
          f"{lateral[0]:.2f} -> {lateral[-1]:.2f} m")  # fmt: skip
    assert np.linalg.norm(start - old) < 0.1  # frame at the event shows the OLD position
    assert lateral[0] > 1.0 and lateral[-1] < 0.1  # converges to the new lane
    assert all(a >= b - 0.05 for a, b in zip(lateral, lateral[1:], strict=False))  # monotone


def test_segment_table_describes_the_lane_graph():
    sim = _sim()
    table = segment_table(sim.lg)
    assert len(table) == sim.lg.n and format_for(sim.lg).bytes_per_vehicle == 9
    assert [t["id"] for t in table] == sim.lg.ids
    assert all(0 <= b < len(table) for t in table for b in t["next"])
    assert max(t["length_m"] for t in table) < 655.35  # a u16 of centimetres


def test_placement_fixture_is_current():
    """The network, segment table and server poses the TypeScript placement test reads."""
    from tools.gen_golden_frame import placement

    doc = json.loads((FIXTURE_DIR / "placement.json").read_text(encoding="utf-8"))
    assert doc == json.loads(json.dumps(placement())), (
        "run `python tools/gen_golden_frame.py` in backend/ and commit the fixtures"
    )
