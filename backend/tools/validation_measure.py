"""The measurements behind the Validation tab (one function per item; see gen_validation.py).

Each returns an item dict: id, title, what, headline (measured value, reference, verdict), an
optional table, reference text + source, and the commands that reproduce it. Measuring code is
the code of the validation tests (tests/validation, tests/engine) wherever one exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.validation.ring import run_ring, wave_speed  # noqa: E402
from trafficsim.engine.calibration import saturation_flows  # noqa: E402
from trafficsim.engine.loop import Simulation  # noqa: E402
from trafficsim.engine.params.control import (  # noqa: E402
    CRITICAL_GAP_MINOR_LEFT_S,
    CRITICAL_GAP_MINOR_RIGHT_S,
    FOLLOW_UP_MINOR_LEFT_S,
    FOLLOW_UP_MINOR_RIGHT_S,
)
from trafficsim.engine.presets import DEFAULT_DEMAND  # noqa: E402
from trafficsim.engine.scenario import DEFAULT_MIX, OdFlow, Scenario  # noqa: E402
from trafficsim.network.demo import build_demo_network  # noqa: E402

PY = ".venv/Scripts/python"
RING_DENSITIES, RING_S, RING_FROM_S = (30, 45, 60, 70, 80), 900.0, 600.0
EMPIRICAL_WAVE_KMH = (-20.0, -10.0)
FD_DENSITIES, FD_S = (20, 30, 40, 50, 55, 60, 65), 600.0
CAPACITY_RANGE = (1800.0, 2400.0)
J1_THROUGH = ("eb_surf_w:1>eb_surf_e:1", "wb_surf_e:1>wb_surf_w:1", "n1_in:0>s1_out:0")
J2_S = 900.0


def _verdict(ok: bool, yes: str = "agrees", no: str = "differs") -> str:
    return yes if ok else no


def ring_waves() -> dict:
    rows, waves = [], {}
    for rho in RING_DENSITIES:
        sim, ts, xs, vs, L, _ = run_ring(rho, RING_S)
        v = vs[ts >= RING_FROM_S]
        w = wave_speed(ts, xs, vs, L, RING_S - RING_FROM_S) * 3.6
        waves[rho] = float(w)
        stopped = f"{(v < 0.5).mean():.0%}"
        rows.append([rho, round(v.mean() * 3.6, 1), round(v.std(axis=1).mean() * 3.6, 2),
                     stopped, round(rho * v.mean() * 3.6), round(float(w), 1)])  # fmt: skip
    lo, hi = EMPIRICAL_WAVE_KMH
    ok = all(lo <= waves[r] <= hi for r in (70, 80))
    return {
        "id": "ring_waves", "title": "Ring road: stop-and-go waves",
        "what": "Cars only, one lane, a 1 km ring in exact IDM equilibrium with one vehicle "
        "disturbed to half speed; the last 5 of 15 simulated minutes are measured. The "
        "disturbance must die out at low density and grow into jams that travel upstream.",
        "headline": {"label": "jam wave speed at 70 and 80 veh/km", "unit": "km/h",
                     "measured": f"{waves[70]:.1f} and {waves[80]:.1f}",
                     "reference": f"{lo:.0f} to {hi:.0f}", "verdict": _verdict(ok)},
        "table": {"columns": ["density veh/km", "mean speed km/h", "speed sd across vehicles km/h",
                              "stopped", "flow veh/h", "wave speed km/h"], "rows": rows},
        "reference": {"text": "Empirically observed stop-and-go waves move against the traffic at "
                      "about -10 to -20 km/h.",
                      "source": "Kerner and Rehborn 1996 (about -15 km/h); Treiber and Kesting "
                      "2013, Traffic Flow Dynamics, Ch. 18; ring experiment after Sugiyama et al. "
                      "2008"},
        "commands": [f"cd backend && {PY} -m pytest tests/validation/test_ring_road.py -s",
                     f"cd backend && {PY} tools/gen_validation.py --only ring_waves"],
    }  # fmt: skip


def lane_capacity() -> dict:
    rows = []
    for rho in FD_DENSITIES:
        _, ts, _, vs, _, _ = run_ring(rho, FD_S)
        v = vs[ts >= FD_S / 2]
        rows.append([rho, round(rho * v.mean() * 3.6), round(v.mean() * 3.6, 1),
                     f"{(v < 0.5).mean():.0%}"])  # fmt: skip
    q_max = max(r[1] for r in rows)
    at = next(r[0] for r in rows if r[1] == q_max)
    lo, hi = CAPACITY_RANGE
    return {
        "id": "lane_capacity", "title": "Free-flow lane capacity (fundamental diagram)",
        "what": "Maximum of flow = density x mean speed over homogeneous ring runs of cars.",
        "headline": {"label": f"maximum lane flow (at {at} veh/km)", "unit": "veh/h",
                     "measured": str(q_max), "reference": f"{lo:.0f} to {hi:.0f}",
                     "verdict": _verdict(lo <= q_max <= hi)},
        "table": {"columns": ["density veh/km", "flow veh/h", "mean speed km/h", "stopped"],
                  "rows": rows},
        "reference": {"text": "Single-lane capacities of about 1,800-2,400 veh/h for cars (basic "
                      "segments up to 2,400 pc/h/ln; urban arterials lower).",
                      "source": "HCM 6th ed., basic freeway segments"},
        "commands": [f"cd backend && {PY} -m pytest tests/validation/test_capacity.py -s "
                     "-k fundamental",
                     f"cd backend && {PY} tools/gen_validation.py --only lane_capacity"],
    }  # fmt: skip


def stop_line() -> dict:
    net = build_demo_network()
    cars = saturation_flows(net, (("car", 1.0),), "J1")
    mixed = saturation_flows(net, DEFAULT_MIX, "J1")
    rows = [[c, round(cars[c]), round(mixed[c])] for c in J1_THROUGH]
    mean_cars = float(np.mean([cars[c] for c in J1_THROUGH]))
    return {
        "id": "stop_line", "title": "Stop-line discharge (saturation flow) at J1",
        "what": "Standing queues of 24 vehicles are released at J1's stop lines; the headways "
        "after the fourth vehicle are averaged (engine/calibration.py).",
        "headline": {"label": "through lanes, cars only (mean of 3)", "unit": "veh/h/lane",
                     "measured": str(round(mean_cars)), "reference": "1,900 (HCM base)",
                     "verdict": _verdict(abs(mean_cars - 1900) / 1900 < 0.05, "agrees",
                                         f"{(mean_cars / 1900 - 1):+.0%} against HCM")},
        "table": {"columns": ["through movement", "cars only veh/h", "default mix veh/h"],
                  "rows": rows},
        "reference": {"text": "HCM base saturation flow 1,900 pc/h/ln; IRC:SP:41 gives 525 PCU/h "
                      "per metre of approach width (about 1,840 for 3.5 m). The mix is counted "
                      "in vehicles, not PCU, so it is lower by construction.",
                      "source": "HCM 6th ed., Ch. 19; IRC:SP:41"},
        "commands": [f"cd backend && {PY} -m pytest tests/validation/test_capacity.py -s "
                     "-k saturation",
                     f"cd backend && {PY} tools/gen_validation.py --only stop_line"],
    }  # fmt: skip


def _j2_run(extra: OdFlow):
    base = (OdFlow("W", "E", 900.0), OdFlow("E", "W", 700.0), OdFlow("N2", "E", 150.0))
    sim = Simulation(build_demo_network(2), Scenario(seed=11, duration_s=J2_S,
                     demand=base + (extra,), signal_control="uncontrolled"))  # fmt: skip
    sim.run_until(J2_S)

    def flow(cid: str) -> float:
        n = sum(1 for e in sim.log.junction_entries if sim.lg.ids[e.conn] == cid)
        return n / J2_S * 3600

    return sim, flow


def _hcm_capacity(vc: float, tc: float, tf: float) -> float:
    return float(vc * np.exp(-vc * tc / 3600) / (1 - np.exp(-vc * tf / 3600)))


def j2_turn(kind: str) -> dict:
    right = kind == "right"
    sim, flow = _j2_run(OdFlow("N2", "W" if right else "E", 900.0))
    conn = "n2_in:1>wb_e2:1" if right else "n2_in:0>eb_out:0"
    east = flow("eb_e2:0>eb_out:0") + flow("eb_e2:1>eb_out:1")
    vc = east + (flow("wb_in:1>wb_e2:1") + flow("wb_in:1>n2_out:0") if right else 0.0)
    tc = CRITICAL_GAP_MINOR_RIGHT_S[2] if right else CRITICAL_GAP_MINOR_LEFT_S[2]
    tf = FOLLOW_UP_MINOR_RIGHT_S if right else FOLLOW_UP_MINOR_LEFT_S
    hcm, served = _hcm_capacity(vc, tc, tf), flow(conn)
    seg = sim.lg.seg_of[conn]
    gaps = np.array([g for _, cc, g in sim.gates.accepted_gaps if cc == seg])
    name = "right turn (crosses both eastbound lanes)" if right else "left turn (merges east)"
    return {
        "id": f"j2_{kind}", "title": f"J2 gap acceptance: minor {name}",
        "what": "The minor movement is saturated (900 veh/h demand); a vehicle enters only if "
        f"every conflicting priority vehicle is at least the critical gap ({tc} s) from the "
        "conflict point. Capacity is compared with HCM's gap-acceptance formula for the "
        "measured conflicting flow.",
        "headline": {"label": f"served flow at {vc:.0f} veh/h conflicting", "unit": "veh/h",
                     "measured": f"{served:.0f}", "reference": f"{hcm:.0f} (HCM capacity)",
                     "verdict": f"{served / hcm:.0%} of HCM"},
        "table": {"columns": ["quantity", "value"],
                  "rows": [["conflicting flow veh/h", round(vc)],
                           ["HCM capacity veh/h", round(hcm)],
                           ["simulation served veh/h", round(served)],
                           ["critical gap used s", tc], ["follow-up headway (HCM, not used) s", tf],
                           ["smallest accepted gap s", round(float(gaps.min()), 2) if gaps.size
                            else None],
                           ["accepted gaps", int(gaps.size)]]},
        "reference": {"text": "c_p = v_c e^(-v_c t_c / 3600) / (1 - e^(-v_c t_f / 3600)) with "
                      f"t_c = {tc} s, t_f = {tf} s (four-lane major road, mirrored for left-hand "
                      "traffic).",
                      "source": "HCM 6th ed., Ch. 20 (two-way stop-controlled), Exhibit 20-11"},
        "notes": [] if right else [
            "New measurement on the current two-lane minor approach. The README's older left-turn "
            "table (156 against 287 veh/h) was made with one shared minor lane, before the "
            "approach was split. Here the simulation serves MORE than HCM's formula gives. Not "
            "isolated: the formula is evaluated with all eastbound through flow as conflicting "
            "(HCM uses the near lane for a minor movement onto a four-lane road), the left-turn "
            "lane no longer waits behind right-turners, and the formula assumes random arrivals "
            "while the real stream is bunched. Treat it as 'not validated against HCM' rather "
            "than as agreement."],
        "commands": [*([f"cd backend && {PY} -m pytest tests/engine/test_j2_minor_lanes.py "
                        "-s -k hcm"] if right else []),
                     f"cd backend && {PY} tools/gen_validation.py --only j2_{kind}"],
    }  # fmt: skip


def webster() -> dict:
    sim = Simulation(build_demo_network(), Scenario(duration_s=60.0, demand=DEFAULT_DEMAND))
    plan = sim.signals[0].plan
    c0 = (1.5 * plan.lost_s + 5.0) / (1.0 - plan.Y)
    return {
        "id": "webster", "title": "Webster's cycle calculation (J1)",
        "what": "The fixed-time plan is built from measured saturation flows and start-up "
        "losses, ITE intergreens and the default demand; the optimum cycle is recomputed here "
        "from the plan's own critical flow ratio and lost time.",
        "headline": {"label": "unbounded optimum cycle C0", "unit": "s",
                     "measured": f"{plan.c0_s:.1f}", "reference": f"{c0:.1f} (formula)",
                     "verdict": _verdict(abs(plan.c0_s - c0) < 1e-6, "agrees", "differs")},
        "table": {"columns": ["quantity", "value"],
                  "rows": [["critical flow ratios y per phase",
                            ", ".join(f"{y:.3f}" for y in plan.y)],
                           ["Y = sum of y", round(plan.Y, 3)],
                           ["lost time L s", round(plan.lost_s, 1)],
                           ["C0 = (1.5 L + 5) / (1 - Y) s", round(c0, 1)],
                           ["applied cycle s (capped at 120 s, IRC:93)", round(plan.cycle_s, 1)],
                           ["greens s", ", ".join(f"{g:.1f}" for g in plan.greens_s)]]},
        "reference": {"text": "Webster's optimum cycle C0 = (1.5 L + 5) / (1 - Y); the applied "
                      "cycle is limited to 120 s.", "source": "Webster's formula as implemented "
                      "in engine/webster.py; cycle cap IRC:93"},
        "commands": [f"cd backend && {PY} -m pytest tests/engine/test_signals.py -s -k webster",
                     f"cd backend && {PY} tools/gen_validation.py --only webster"],
    }  # fmt: skip


MEASURES = {"ring_waves": ring_waves, "lane_capacity": lane_capacity, "stop_line": stop_line,
            "j2_left": lambda: j2_turn("left"), "j2_right": lambda: j2_turn("right"),
            "webster": webster}  # fmt: skip
