"""Merge alternation (engine/merge_turns.py): lanes that merge into one exit lane take turns."""

from dataclasses import replace

import numpy as np
import pytest

from trafficsim.engine.lanegraph import compile_network
from trafficsim.engine.loop import Simulation
from trafficsim.engine.merge_turns import MergeTurns
from trafficsim.network.demo import build_demo_network
from trafficsim.network.structure import Structure
from trafficsim.server.experiments import definitions
from trafficsim.server.scenario_doc import parse, to_engine


def _turns(net):
    lg = compile_network(net)
    yields = {lg.seg_of[c.id] for c in net.connectors if c.junction_id and c.yields}
    return lg, MergeTurns(lg, yields)


def _observe(t, queued, ok):
    """One step: the connectors in `queued` have a vehicle standing at the line."""
    rows = list(range(len(queued)))
    t.observe(np.zeros(len(rows)), np.ones(len(rows)), np.array(queued), rows, lambda c: c in ok)


def test_the_two_through_lanes_of_j1_are_merge_rivals_and_the_minor_road_is_not():
    net = build_demo_network(Structure(2, 3, 2, 3.5, 3.5))  # 3 surface lanes: 2 through lanes
    lg, t = _turns(net)
    a, b = lg.seg_of["eb_surf_w:1>eb_surf_e:0"], lg.seg_of["eb_surf_w:2>eb_surf_e:0"]
    assert b in t.rivals[a] and a in t.rivals[b]
    for c in net.connectors:  # J2: the minor movement merges into the major exit lane
        if c.junction_id == "J2":
            assert lg.seg_of[c.id] not in t.rivals or not t.rivals[lg.seg_of[c.id]]


def test_greens_alternate_between_two_queued_lanes_and_an_owner_keeps_its_green():
    net = build_demo_network(Structure(2, 3, 2, 3.5, 3.5))
    lg, t = _turns(net)
    a, b = lg.seg_of["eb_surf_w:1>eb_surf_e:0"], lg.seg_of["eb_surf_w:2>eb_surf_e:0"]
    to = int(lg.conn_to[a])
    both = {a, b}
    _observe(t, [a, b], both)  # green starts, both lanes have a queue
    assert not t.must_yield(a, to) and not t.must_yield(b, to)  # nobody has had a turn yet
    t.granted(a, to)  # a is served first and owns this green
    assert t.must_yield(b, to) and not t.must_yield(a, to)
    _observe(t, [b], both)  # a's queue has gone from the line: b may use the rest of the green
    assert not t.must_yield(b, to)
    _observe(t, [a, b], set())  # red
    _observe(t, [a, b], both)  # the next green: a had the last one, so a yields to b
    assert t.must_yield(a, to) and not t.must_yield(b, to)
    t.granted(b, to)
    _observe(t, [a, b], set())
    _observe(t, [a, b], both)  # and then it is a's turn again
    assert t.must_yield(b, to) and not t.must_yield(a, to)


def test_no_yielding_to_a_rival_that_is_not_queued_or_not_allowed_to_go():
    net = build_demo_network(Structure(2, 3, 2, 3.5, 3.5))
    lg, t = _turns(net)
    a, b = lg.seg_of["eb_surf_w:1>eb_surf_e:0"], lg.seg_of["eb_surf_w:2>eb_surf_e:0"]
    to = int(lg.conn_to[a])
    _observe(t, [a, b], {a, b})
    t.granted(a, to)
    _observe(t, [a, b], set())
    _observe(t, [a], {a, b})  # next green, but b has nobody waiting
    assert not t.must_yield(a, to)
    _observe(t, [a, b], set())
    _observe(t, [a, b], {a})  # b's signal is red
    assert not t.must_yield(a, to)


@pytest.mark.slow
def test_with_the_flyover_closed_both_through_lanes_of_j1_are_served():
    """The case that exposed the bug: before the rule the middle lane got 0 veh/h after the
    first green, from a queue of about 65 vehicles."""
    _, a, _b = definitions()["surface_closed"]["comparisons"][0]
    p = parse(a)
    sim = Simulation(
        build_demo_network(p.structure.to_network()),
        replace(to_engine(p), seed=1, duration_s=900.0),
    )
    lg = sim.lg
    sim.run_until(900.0)
    n = {
        k: sum(
            1
            for e in sim.log.junction_entries
            if lg.ids[e.conn] == f"eb_surf_w:{k}>eb_surf_e:0" and e.t >= 300.0
        )
        for k in (1, 2)
    }
    print(f"\n[merge] through entries 300-900 s: lane 1 {n[1]}, lane 2 {n[2]}")
    assert min(n.values()) >= 0.3 * max(n.values()) > 0
