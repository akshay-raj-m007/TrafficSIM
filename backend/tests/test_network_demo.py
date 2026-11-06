"""The demo network must visibly contain every element of the brief, in true metres."""

import numpy as np
import pytest

from trafficsim.network import geometry as geo
from trafficsim.network import validate
from trafficsim.network.routing import fastest_route
from trafficsim.network.serialize import network_to_dict


def test_has_roads_with_1_2_3_and_4_lanes(net):
    assert {1, 2, 3, 4} <= validate.lane_counts(net)


def test_two_junctions_one_signalised_one_give_way(net):
    controls = sorted(j.control for j in net.junctions)
    assert controls == ["give_way", "signalised"]
    j2 = next(j for j in net.junctions if j.control == "give_way")
    assert j2.minor_approach_lanes, "give-way junction needs a minor approach"
    yielding = [c for c in net.connectors if c.junction_id == j2.id and c.yields]
    assert {net.lane(c.from_lane).road_id for c in yielding} >= {"n2_in"}


def test_lane_drop_three_to_two(net):
    dropped = validate.dropped_lanes(net)
    assert dropped == ["eb_e3:0"]
    road = net.road_of(dropped[0])
    assert road.n_lanes == 3
    nxt = {net.road_of(c.to_lane).n_lanes for ln in road.lanes for c in net.successors(ln.id)}
    assert nxt == {2}


@pytest.mark.parametrize("jid", ["J1", "J2"])
def test_turning_movements_not_just_through(net, jid):
    moves = {c.movement for c in net.connectors if c.junction_id == jid}
    assert moves == {"left", "through", "right"}


def test_turn_paths_have_real_length(net):
    for c in net.connectors:
        if c.junction_id is None:
            assert c.length_m == 0.0
        else:
            assert c.length_m > 5.0


def test_flyover_with_diverge_and_merge_ramps(net):
    kinds = {r.kind for r in net.roads}
    assert {"flyover", "ramp"} <= kinds
    w4 = net.road("eb_w4")
    targets = {net.road_of(c.to_lane).kind for ln in w4.lanes for c in net.successors(ln.id)}
    assert targets == {"surface", "ramp"}  # lane-level diverge
    e3_sources = {
        net.road_of(c.from_lane).kind for c in net.connectors if c.to_lane.startswith("eb_e3:")
    }
    assert e3_sources == {"surface", "ramp"}  # merge


@pytest.mark.parametrize(
    ("o", "d", "uses_flyover"),
    [("W", "E", True), ("E", "W", True), ("W", "N1", False), ("W", "S1", False)],
)
def test_route_choice_depends_on_destination(net, o, d, uses_flyover):
    route = fastest_route(net, o, d)
    assert route is not None
    on_flyover = any(net.road(r).kind == "flyover" for r in route)
    assert on_flyover is uses_flyover


def test_every_od_pair_is_reachable(net):
    zones = [z.id for z in net.zones]
    for o in zones:
        for d in zones:
            if o != d:
                assert fastest_route(net, o, d) is not None, (o, d)


def test_adjacent_lane_centrelines_are_exactly_half_widths_apart(net):
    """1 unit = 1 metre: no scaling of lane offsets."""
    for r in net.roads:
        for a, b in zip(r.lanes[:-1], r.lanes[1:], strict=True):
            expected = (a.width_m + b.width_m) / 2
            for pa in a.centreline:
                d = geo.point_to_polyline_xy(pa, b.centreline)
                assert d == pytest.approx(expected, abs=1e-9), (a.id, b.id)


def test_widths_vary_across_network(net):
    widths = {ln.width_m for r in net.roads for ln in r.lanes}
    assert widths == {2.75, 3.0, 3.25, 3.5}


def test_links_join_coincident_endpoints(net):
    for c in net.connectors:
        a, b = net.lane(c.from_lane), net.lane(c.to_lane)
        np.testing.assert_allclose(c.path[0], a.centreline[-1], atol=1e-9)
        np.testing.assert_allclose(c.path[-1], b.centreline[0], atol=1e-9)


def test_offset_is_exact_on_curves():
    arc = np.array([[np.cos(t) * 50, np.sin(t) * 50, 0.0] for t in np.linspace(0, 1.5, 40)])
    inner = geo.offset_left(arc, 3.5)
    for p in inner[1:-1]:
        assert geo.point_to_polyline_xy(p, arc) == pytest.approx(3.5, abs=1e-9)


def test_serialisation_round_trips_key_fields(net):
    d = network_to_dict(net)
    assert d["meta"]["units"] == "m" and d["meta"]["drive_side"] == "left"
    assert len(d["roads"]) == len(net.roads)
    lane = d["roads"][0]["lanes"][0]
    assert set(lane) == {"id", "index", "width_m", "length_m", "centreline"}
    assert {j["id"] for j in d["junctions"]} == {"J1", "J2"}
