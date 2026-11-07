"""Per-run metrics: warm-up exclusion, unfinished trips, paired arrivals, determinism."""

import pytest

from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import DEFAULT_DEMAND, scaled
from trafficsim.engine.runmetrics import METRICS, Trip, flyover_pairs, run_metrics, summarise
from trafficsim.engine.scenario import Scenario, SetFlyover, SetPolicy

WE = ("W", "E")
NO = set()


def trip(t_gen, t_exit, ff=100.0, od=("W", "N1"), vid=0):
    return Trip(t_gen, t_exit, ff, od, vid)


# ----------------------------------------------------------------- the rules (pure) ----
def test_nothing_before_the_warm_up_enters_any_trip_metric():
    early = [trip(10.0, 400.0, vid=1), trip(50.0, 90000.0, vid=2)]  # extreme, generated early
    late = [trip(300.0, 420.0, vid=3), trip(310.0, 450.0, vid=4)]  # delay 20 s and 40 s
    base = summarise(late, 300.0, 900.0, set(), NO, 0)
    with_early = summarise(early + late, 300.0, 900.0, set(), NO, 0)
    for k in ("mean_delay_s", "mean_delay_completed_s", "tt_p50_s", "tt_p90_s", "unfinished_veh"):
        assert with_early[k] == base[k], k
    assert base["mean_delay_s"] == pytest.approx(30.0)
    assert with_early["counts"]["cohort"] == 2


def test_throughput_is_a_flow_of_exits_inside_the_window():
    trips = [trip(10.0, 250.0), trip(100.0, 350.0), trip(300.0, 500.0), trip(320.0, 899.0)]
    out = summarise(trips, 300.0, 900.0, set(), NO, 0)
    assert out["counts"]["exits_in_window"] == 3  # the one that exited at 250 s is warm-up
    assert out["throughput_veh_h"] == pytest.approx(3 / (600 / 3600))


def test_unfinished_trips_count_with_a_lower_bound_instead_of_vanishing():
    done = [trip(300.0, 420.0, ff=100.0)]  # delay 20
    stuck = [trip(310.0, None, ff=100.0)]  # at 900 s: 590 s elapsed, lower bound 490
    young = [trip(850.0, None, ff=100.0)]  # only 50 s elapsed < free flow: cannot count
    out = summarise(done + stuck + young, 300.0, 900.0, set(), NO, 1)
    assert out["mean_delay_completed_s"] == pytest.approx(20.0)
    assert out["mean_delay_s"] == pytest.approx((20.0 + 490.0) / 2)  # headline sees the stuck one
    assert out["unfinished_veh"] == 1 and out["unserved_veh"] == 1
    assert out["counts"]["too_young"] == 1 and out["counts"]["cohort"] == 2
    only_completed = summarise(done, 300.0, 900.0, set(), NO, 0)
    assert out["mean_delay_s"] > only_completed["mean_delay_s"]  # dropping them would flatter


def test_flyover_share_is_over_eligible_completed_trips_only():
    trips = [trip(300.0, 440.0, od=WE, vid=1), trip(301.0, 450.0, od=WE, vid=2),
             trip(302.0, 450.0, od=("W", "N1"), vid=3)]  # fmt: skip
    out = summarise(trips, 300.0, 900.0, {1, 3}, {WE}, 0)
    assert out["flyover_share"] == pytest.approx(0.5)  # vid 3 is not eligible, vid 2 did not use it
    assert summarise([trip(300.0, 440.0)], 300.0, 900.0, set(), {WE}, 0)["flyover_share"] is None


def test_the_eligible_pairs_are_those_whose_fastest_open_route_uses_the_flyover(net):
    # W<->E through trips, and W<->N2 (the fastest way to the J2 minor road also takes the deck)
    assert flyover_pairs(net) == {("W", "E"), ("E", "W"), ("W", "N2"), ("N2", "W")}


def test_warm_up_must_lie_inside_the_run(net):
    with pytest.raises(ValueError, match="warm-up"):
        run_metrics(net, Scenario(duration_s=100.0, demand=DEFAULT_DEMAND), 100.0)


# ------------------------------------------------------------------- whole runs --------
SHORT = dict(duration_s=300.0, demand=scaled(DEFAULT_DEMAND, 1.3))


@pytest.mark.slow
def test_a_run_against_itself_gives_identical_metrics(net):
    a = run_metrics(net, Scenario(seed=5, **SHORT), 100.0)
    b = run_metrics(net, Scenario(seed=5, **SHORT), 100.0)
    assert a == b
    assert set(METRICS) <= set(a) and a["counts"]["cohort"] > 0


def _arrivals(sim):
    """Every generated vehicle as (arrival time, class, origin, destination)."""
    rt = sim.routes
    out = []
    for e in sim.log.exits:
        out.append((e.t_gen, e.cls, *rt.pair[e.route]))
    vs = sim.vehicles
    for i in range(vs.n):
        out.append((float(vs.t_gen[i]), int(vs.cls[i]), *rt.pair[int(vs.route[i])]))
    for z in sim.demand.zones:
        out += [(q.t_gen, q.cls, *rt.pair[q.route]) for q in z.queue]
    return sorted(out)


@pytest.mark.slow
def test_paired_seeds_give_identical_arrivals_whatever_the_control(net):
    """The common-random-numbers claim: signals and flyover state do not move arrivals."""
    mid = ((50, SetPolicy("max_pressure_threshold")), (120, SetFlyover(False)))
    variants = [{}, {"signal_control": "max_pressure"}, {"flyover_open": False}, {"changes": mid}]
    runs = []
    for kw in variants:
        sim = Simulation(
            net, Scenario(seed=9, duration_s=200.0, demand=scaled(DEFAULT_DEMAND, 1.3), **kw)
        )
        sim.run_until(200.0)
        runs.append(_arrivals(sim))
    assert len(runs[0]) > 150
    assert all(r == runs[0] for r in runs[1:])


def test_a_closure_detour_counts_as_delay_against_the_open_network_route(net):
    """Delay is measured against the fastest route on the OPEN network, so a lone car that has
    to take the surface because the flyover is closed shows the detour as delay."""
    from trafficsim.engine.freeflow import DelayReference, reference_for

    times = {}
    for open_ in (True, False):
        sim = Simulation(
            net,
            Scenario(duration_s=500.0, signal_control="uncontrolled", flyover_open=open_),
        )
        sim.place_vehicle("W", "E", "car", 0, 20.0, 10.0)
        while not sim.log.exits and sim.step():
            pass
        e = sim.log.exits[0]
        times[open_] = e.t_exit - e.t_ins
        ref = DelayReference(net, reference_for(net, sim.lg))
        ref.ref.request([(ref.roads(("W", "E")), e.cls)], background=False)
        times[f"ff{open_}"] = ref.free_flow(sim.routes.pair[e.route], e.cls)
    assert times["ffTrue"] == times["ffFalse"]  # one reference for everybody
    assert times[True] - times["ffTrue"] < 5.0  # open: about free flow (it entered at speed)
    assert times[False] - times["ffFalse"] > times[True] - times["ffTrue"] + 5.0  # the detour
    print(f"\n[detour] open {times[True]:.1f} s, closed {times[False]:.1f} s, open-route free "
          f"flow {times['ffTrue']:.1f} s -> delay {times[True] - times['ffTrue']:.1f} s vs "
          f"{times[False] - times['ffFalse']:.1f} s")  # fmt: skip
