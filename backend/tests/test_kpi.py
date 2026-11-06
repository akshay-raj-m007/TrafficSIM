"""Measured KPIs: detectors, queues, delay, unserved demand, snapshot.

Each number is re-derived independently from raw simulation state, not from the counters
that produced it.
"""

import json

import pytest

from tests.helpers import straight_network
from trafficsim.engine.detectors import DetectorSpec
from trafficsim.engine.freeflow import (
    TABLE_PATH,
    FreeFlowReference,
    all_keys,
    input_digest,
    reference_for,
)
from trafficsim.engine.kpi import KPI_DEFS, KpiLayout
from trafficsim.engine.lanegraph import compile_network
from trafficsim.engine.loop import Simulation
from trafficsim.engine.params.control import DETECTOR_WINDOW_S, V_QUEUED_MPS
from trafficsim.engine.presets import DEMO_DEMAND, DEMO_KPI_LAYOUT
from trafficsim.engine.queues import QUEUE_MAX_GAP_M, ApproachSpec
from trafficsim.engine.scenario import OdFlow, Scenario


# ---------------------------------------------------------------- detectors ---------------
def test_detector_counts_every_vehicle_exactly_once_and_windows_flow():
    spec = DetectorSpec("D", "line", "main", 1500.0)
    sim = Simulation(
        straight_network(length_m=3000.0),
        Scenario(seed=2, duration_s=200.0, demand=(OdFlow("A", "B", 900.0),)),
        KpiLayout((spec,), ()),
    )
    prev, times = {}, []
    for _ in range(2000):
        sim.step()
        vs = sim.vehicles
        cur = dict(zip(vs.vid.tolist(), vs.s.tolist(), strict=True))
        times += [sim.time_s for vid, s in cur.items() if vid in prev and prev[vid] < 1500.0 <= s]
        prev = cur
    d = sim.kpis.detectors
    t = sim.time_s
    beyond = int((sim.vehicles.s >= 1500.0).sum())
    window = sum(1 for x in times if x > t - DETECTOR_WINDOW_S)
    print(f"\n[detector] total {int(d.total[0])} = {beyond} on road beyond the line "
          f"+ {sim.exited} exited; last-60 s count {d.window_count(0, t)} "
          f"(brute force {window})")  # fmt: skip
    assert d.total[0] == beyond + sim.exited == len(times)
    assert d.window_count(0, t) == window
    assert d.flow_veh_per_h(0, t) == pytest.approx(window * 60.0)


def test_detectors_stay_away_from_road_ends():
    with pytest.raises(ValueError):
        Simulation(
            straight_network(length_m=500.0), Scenario(duration_s=1.0),
            KpiLayout((DetectorSpec("D", "x", "main", 490.0),), ()),
        )  # fmt: skip


# ------------------------------------------------------------------- queues ---------------
def _queue_sim(cars):
    sim = Simulation(straight_network(length_m=500.0), Scenario(duration_s=10.0),
                     KpiLayout((), (ApproachSpec("Q", "q", "main"),)))  # fmt: skip
    for s, v in cars:
        sim.place_vehicle("A", "B", "car", 0, s, v)
    return sim.kpis.queues.measure(sim.vehicles)[0]


def test_queue_is_the_unbroken_chain_from_the_stop_line_by_hand():
    # three stopped cars bumper-to-bumper from the line, a gap of 11.5 m, one more car
    # (outside the chain) and a moving car far upstream
    n, length = _queue_sim([(499.0, 0.0), (492.5, 0.0), (486.0, 0.0), (470.0, 0.0), (300.0, 10.0)])
    print(f"\n[queue] by hand: 3 vehicles, 500 - (486 - 4.5) = 18.5 m; measured {n} veh, "
          f"{length:.1f} m (max gap {QUEUE_MAX_GAP_M:.2f} m)")  # fmt: skip
    assert (n, length) == (3, pytest.approx(18.5))


@pytest.mark.parametrize(
    ("cars", "expected"),
    [
        ([(480.0, 0.0)], (0, 0.0)),  # first vehicle 20 m from the line: no queue
        ([(499.0, V_QUEUED_MPS + 0.5)], (0, 0.0)),  # too fast to count as queued
        ([(499.0, 0.0), (480.0, 0.0)], (1, 5.5)),  # 14.5 m gap breaks the chain
        ([(499.0, V_QUEUED_MPS - 0.1)], (1, 5.5)),  # crawling counts
    ],
)
def test_queue_edge_cases(cars, expected):
    n, length = _queue_sim(cars)
    assert (n, length) == (expected[0], pytest.approx(expected[1]))


# ----------------------------------------------------------- free-flow reference -----------
def test_committed_freeflow_table_is_current(net):
    lg = compile_network(net)
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    assert table["digest"] == input_digest(net, lg), (
        "the lane graph, vehicle classes or a model constant changed: run "
        "`python tools/gen_freeflow.py` in backend/ and commit the new table"
    )
    assert {(tuple(e["roads"]), e["cls"]) for e in table["values"]} == set(all_keys(net))
    assert reference_for(net, lg).table_used


@pytest.mark.slow
def test_freeflow_table_equals_a_fresh_measurement(net):
    table = {(tuple(e["roads"]), e["cls"]): e["t_s"]
             for e in json.loads(TABLE_PATH.read_text(encoding="utf-8"))["values"]}  # fmt: skip
    keys = all_keys(net)
    sample = [keys[0], keys[7], keys[len(keys) // 2], keys[-1]]
    fresh = FreeFlowReference(net)  # no lane graph given -> no table, measure from scratch
    fresh.request(sample, background=False)
    for k in sample:
        print(f"[free flow] {k[0][0]}->{k[0][-1]} class {k[1]}: table {table[k]:.3f} s, "
              f"fresh {fresh.get(*k):.3f} s")  # fmt: skip
        assert fresh.get(*k) == pytest.approx(table[k], abs=1e-3)


# ------------------------------------------------------------------- delay ----------------
def test_a_lone_vehicle_has_zero_delay_by_construction(net):
    """Same engine, same insertion, same route, empty network: delay must be 0."""
    sim = Simulation(net, Scenario(duration_s=400.0, signal_control="uncontrolled"),
                     DEMO_KPI_LAYOUT)  # fmt: skip
    route = sim.routes.add(net, sim.lg, "W", "E")
    assert sim.demand.insert_now(sim.vehicles, route, 0, 0.0) is not None
    while sim.exited == 0:
        sim.step()
    d = sim.kpi_snapshot()["delay"]
    print(f"\n[delay] lone car W->E: delay {d['mean_s']} s (n = {d['n']})")
    assert d["reference_ready"] and d["n"] == 1 and d["mean_s"] == pytest.approx(0.0, abs=0.01)


@pytest.mark.slow
def test_mean_delay_matches_manual_recomputation_in_traffic(net):
    sim = Simulation(net, Scenario(seed=9, duration_s=300.0, demand=DEMO_DEMAND),
                     DEMO_KPI_LAYOUT)  # fmt: skip
    sim.run_until(300.0)
    ref = reference_for(net, sim.lg)
    delays = [(e.t_exit - e.t_ins) - ref.get(sim.routes.roads[e.route], e.cls)
              for e in sim.log.exits]  # fmt: skip
    waits = [e.t_ins - e.t_gen for e in sim.log.exits]
    snap = sim.kpi_snapshot()["delay"]
    print(f"[delay] {len(delays)} exits: mean {sum(delays) / len(delays):.2f} s (min "
          f"{min(delays):.2f}); snapshot {snap}")  # fmt: skip
    assert snap["n"] == len(delays)
    assert snap["mean_s"] == pytest.approx(sum(delays) / len(delays), abs=0.006)
    assert snap["entry_wait_mean_s"] == pytest.approx(sum(waits) / len(waits), abs=0.006)
    assert min(delays) > -1.0  # nobody beats the lone-vehicle time by more than rounding/lane luck


# ------------------------------------------------------------------ snapshot --------------
def test_snapshot_is_json_traceable_and_conserves_counts(net):
    sim = Simulation(net, Scenario(seed=3, duration_s=120.0, demand=DEMO_DEMAND,
                                   signal_control="uncontrolled"), DEMO_KPI_LAYOUT)  # fmt: skip
    sim.run_until(120.0)
    snap = json.loads(json.dumps(sim.kpi_snapshot()))  # plain JSON types only
    c = snap["counts"]
    assert c["generated"] == c["active"] + c["exited"] + c["queued"] == sim.demand.generated
    assert snap["unserved"]["queued"] == c["queued"]
    assert sum(snap["unserved"]["by_zone"].values()) == c["queued"]
    assert [f["id"] for f in snap["flow"]] == [s.id for s in DEMO_KPI_LAYOUT.detectors]
    assert [q["id"] for q in snap["queues"]] == [a.id for a in DEMO_KPI_LAYOUT.approaches]
    assert snap["delay"]["reference_ready"] and snap["signal"] is None
    assert set(KPI_DEFS) >= {"flow", "queue", "delay", "unserved", "signal"}
    assert all(q["max_window_m"] >= q["length_m"] for q in snap["queues"])


def test_snapshot_is_deterministic(net):
    def run():
        sim = Simulation(net, Scenario(seed=4, duration_s=90.0, demand=DEMO_DEMAND,
                                       signal_control="uncontrolled"), DEMO_KPI_LAYOUT)  # fmt: skip
        sim.run_until(90.0)
        return json.dumps(sim.kpi_snapshot(), sort_keys=True)

    assert run() == run()
