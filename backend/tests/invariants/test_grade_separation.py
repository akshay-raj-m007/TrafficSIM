"""Invariant 5 — grade separation.

A vehicle on the flyover can never interact with, or turn onto, the road below except
through the defined ramps. At the network level this means:
  * every level change happens on a ramp, never at a junction;
  * flyover roads connect only to ramps/flyover;
  * where the deck passes over ground roadway the vertical clearance is respected.
Vehicle-level checks (leader search confined to the vehicle's own lane) are added in
step 2, once vehicles exist.
"""

import numpy as np
import pytest

from trafficsim.network import geometry as geo
from trafficsim.network.builder import NetworkBuilder
from trafficsim.network.validate import clearance_violations, grade_separation_violations


def test_demo_network_has_no_grade_separation_violations(net):
    assert grade_separation_violations(net) == []


def test_demo_network_clearance(net):
    m = net.meta
    assert clearance_violations(net, m["deck_thickness_m"], m["min_clearance_m"]) == []


def test_flyover_reachable_from_ground_only_via_ramps(net):
    for c in net.connectors:
        a, b = net.road_of(c.from_lane), net.road_of(c.to_lane)
        if "flyover" in (a.kind, b.kind):
            assert {a.kind, b.kind} <= {"flyover", "ramp"}


def test_deck_actually_passes_over_signalised_junction(net):
    j1 = next(j for j in net.junctions if j.id == "J1")
    deck = net.road("eb_flyover")
    xs = deck.reference[:, 0]
    jx0, jx1 = j1.polygon[:, 0].min(), j1.polygon[:, 0].max()
    assert xs.min() < jx0 and xs.max() > jx1
    assert np.all(deck.reference[:, 2] == net.meta["deck_z_m"])


# ---- negative controls: the checkers must catch broken networks -----------------
def _tiny(deck_z: float, connect_directly: bool) -> NetworkBuilder:
    b = NetworkBuilder()
    b.road("ground", "surface", geo.straight(-100, -50, -100, 50), [3.5], 0.0, 50)
    b.road("fly", "flyover", geo.straight(-200, 0, 0, 0, deck_z), [3.5], 0.0, 50)
    b.road("feed", "surface", geo.straight(-300, 0, -200, 0, deck_z), [3.5], 0.0, 50)
    if connect_directly:
        b.link("feed", 0, "fly", 0)  # ground road straight onto the deck: forbidden
    return b


def test_checker_flags_insufficient_clearance():
    net = _tiny(deck_z=4.0, connect_directly=False).build()
    assert clearance_violations(net, 1.0, 5.5)


def test_checker_flags_level_change_without_ramp():
    net = _tiny(deck_z=6.5, connect_directly=True).build()
    assert grade_separation_violations(net)


# ---- vehicle level ------------------------------------------------------------------
@pytest.mark.slow
def test_vehicles_change_level_only_via_ramps(medium):
    """Every observed segment transition is a network edge or a same-road lane change,
    and a vehicle only moves between ground and flyover level on a ramp."""
    sim = medium.sim
    lg = sim.lg
    level = {r.id: r.level for r in sim.network.roads}
    kind = {r.id: r.kind for r in sim.network.roads}
    bad = []
    for a, b in medium.transitions:
        ra, rb = lg.road_of[a], lg.road_of[b]
        edge = b in lg.succ[a]
        lane_change = ra is not None and ra == rb and b in lg.nbr[a]
        change_then_edge = any(b in lg.succ[n] for n in lg.nbr[a] if n >= 0)
        if not (edge or lane_change or change_then_edge):
            bad.append((lg.ids[a], lg.ids[b], "not a network edge"))
        elif ra and rb and level[ra] != level[rb] and "ramp" not in (kind[ra], kind[rb]):
            bad.append((lg.ids[a], lg.ids[b], "level change off-ramp"))
        if (ra and level[ra] == 1 and rb is None) or (rb and level[rb] == 1 and ra is None):
            bad.append((lg.ids[a], lg.ids[b], "flyover <-> junction"))
    deck = ("eb_flyover", "wb_flyover")
    on_fly = sum(1 for _, b in medium.transitions if lg.road_of[b] in deck)
    print(f"\n[grade separation] {len(medium.transitions)} distinct transitions observed, "
          f"{on_fly} onto the flyover deck, violations {bad}")  # fmt: skip
    assert not bad and on_fly > 0
