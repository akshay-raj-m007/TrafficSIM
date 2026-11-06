"""Junction control: conflict geometry, J2 give-way gap acceptance, spillback guard."""

import numpy as np
import pytest

from trafficsim.engine.loop import Simulation
from trafficsim.engine.params.control import FOLLOW_UP_MINOR_LEFT_S
from trafficsim.engine.scenario import Incident, OdFlow, Scenario
from trafficsim.network.conflicts import conflict_table

WARMUP_S = 300.0


def test_conflict_table_matches_geometry(net):
    t = conflict_table(net)
    minor_right = t["n2_in:0>wb_e2:1"]
    assert minor_right["eb_e2:0>eb_out:0"].kind == "cross"  # crosses both EB lanes
    assert minor_right["eb_e2:1>eb_out:1"].kind == "cross"
    assert minor_right["wb_in:1>wb_e2:1"].kind == "merge"  # joins WB lane 1
    assert "n2_in:0>eb_out:0" not in minor_right  # diverging from the same lane
    assert t["n2_in:0>eb_out:0"] == {"eb_e2:0>eb_out:0": t["n2_in:0>eb_out:0"]["eb_e2:0>eb_out:0"]}
    for a, row in t.items():
        for b, cf in row.items():
            assert t[b][a].s_self == cf.s_other  # symmetric conflict points
            ca = next(c for c in net.connectors if c.id == a)
            assert 0.0 < cf.s_self <= ca.length_m + 1e-9


def _minor_left_run(net, major_vph):
    dem = (OdFlow("W", "E", major_vph), OdFlow("N2", "E", 900))  # minor saturated
    sim = Simulation(net, Scenario(seed=11, duration_s=1200.0, demand=dem))
    sim.run_until(1200.0)
    lg = sim.lg
    c_major, c_minor = lg.seg_of["eb_e2:0>eb_out:0"], lg.seg_of["n2_in:0>eb_out:0"]
    ent = [e for e in sim.log.junction_entries if e.t >= WARMUP_S]
    span_h = (1200.0 - WARMUP_S) / 3600.0
    t_major = np.array([e.t for e in ent if e.conn == c_major])
    cap = sum(e.conn == c_minor for e in ent) / span_h
    return sim, t_major, cap, span_h


@pytest.mark.parametrize("major_vph", [400, 1800])
def test_give_way_gap_acceptance_and_capacity(net, major_vph):
    sim, t_major, cap, span_h = _minor_left_run(net, major_vph)
    tc = sim.gates.crit_gap[sim.lg.seg_of["n2_in:0>eb_out:0"]]
    vc = t_major.size / span_h
    hcm = vc * np.exp(-vc * tc / 3600) / (1 - np.exp(-vc * FOLLOW_UP_MINOR_LEFT_S / 3600))
    h = np.diff(t_major)
    usable = (h >= tc).sum() / span_h
    usable_random = vc * np.exp(-vc / 3600 * tc)
    gaps = np.array(
        [g for _, c, g in sim.gates.accepted_gaps if c == sim.lg.seg_of["n2_in:0>eb_out:0"]]
    )
    finite = gaps[np.isfinite(gaps)]
    med = float(np.median(finite)) if finite.size else np.inf
    print(f"\n[give-way] conflicting {vc:.0f} veh/h (headway CV {h.std() / h.mean():.2f}; "
          f"random = 1.0); gaps >= t_c={tc} s per h: {usable:.0f} measured vs "
          f"{usable_random:.0f} if random; minor-left capacity {cap:.0f} veh/h vs HCM "
          f"c_p {hcm:.0f}; accepted gaps min {gaps.min():.2f} / median "
          f"{med:.2f} s")  # fmt: skip
    assert gaps.size > 0 and gaps.min() >= tc  # never accepts a gap below t_c
    assert sim.emergency_brakings == 0 and sim.box_stopped_vehicle_s == 0.0
    if major_vph == 400:  # near-random arrivals: HCM's assumption holds approximately
        assert cap == pytest.approx(hcm, rel=0.30)


def test_spillback_guard_with_blocked_exit(net):
    """Close both N1 exit lanes 80 m before their end: the queue must build upstream of
    J1, never inside it, and every entry must have had room when it committed."""
    lane_len = net.lane("n1_out:0").length_m
    inc = tuple(Incident(f"n1_out:{k}", lane_len - 80.0, 0.0, 1e6) for k in (0, 1))
    dem = (OdFlow("W", "N1", 300), OdFlow("S1", "N1", 300), OdFlow("E", "N1", 200),
           OdFlow("W", "E", 800), OdFlow("N1", "S1", 200))  # fmt: skip
    sim = Simulation(net, Scenario(seed=21, duration_s=900.0, demand=dem, incidents=inc))
    sim.run_until(900.0)
    lg = sim.lg
    into_n1 = {lg.seg_of[c.id] for c in net.connectors if c.to_lane.startswith("n1_out")}
    e_n1 = [e for e in sim.log.junction_entries if e.conn in into_n1]
    late = [e for e in e_n1 if e.t > 600.0]
    vs = sim.vehicles
    on_n1 = np.isin(vs.seg, [lg.seg_of["n1_out:0"], lg.seg_of["n1_out:1"]])
    queued_up = sum(int(np.sum((vs.seg == lg.seg_of[a]) & (vs.v < 0.5))) for a in
                    ("eb_surf_w:0", "s1_in:0", "s1_in:1", "wb_surf_e:0"))  # fmt: skip
    short = sum(e.room < e.need for e in sim.log.junction_entries)
    print(f"\n[spillback] entries into N1 exit: {len(e_n1)} (after t=600 s: {len(late)}); "
          f"vehicles on n1_out {int(on_n1.sum())}; stopped on J1 approaches {queued_up}; "
          f"commit-room < need: {short}; vehicle-seconds held inside junction boxes "
          f"{sim.box_stopped_vehicle_s:.1f}")  # fmt: skip
    assert all(e.room >= e.need for e in sim.log.junction_entries)
    assert sim.box_stopped_vehicle_s == 0.0
    assert not late and queued_up > 0
