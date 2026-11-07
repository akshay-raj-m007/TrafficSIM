"""Structural settings: the default network is reproduced exactly; every allowed structure
builds, compiles, routes, and has consistent geometry."""

import itertools
import json
from pathlib import Path

import numpy as np
import pytest

from tests.network_fingerprint import fingerprint
from trafficsim.engine.lanegraph import compile_network
from trafficsim.engine.routes import RouteTable
from trafficsim.network import validate
from trafficsim.network.conflicts import conflict_table
from trafficsim.network.demo import build_demo_network
from trafficsim.network.demo_corridor import DECK_THICKNESS, MIN_CLEARANCE
from trafficsim.network.routing import fastest_route
from trafficsim.network.structure import LANES_RANGE, WIDTH_RANGE_M, Structure

FIXTURE = Path(__file__).parent / "fixtures" / "default_network.json"
LANES = range(LANES_RANGE[0], LANES_RANGE[1] + 1)
W_MIN, W_MAX = WIDTH_RANGE_M
CORNERS = [Structure(2, s, f, ws, wf) for s, f in itertools.product((1, 4), repeat=2)
           for ws, wf in itertools.product((W_MIN, W_MAX), repeat=2)]  # fmt: skip
ALL = [Structure(2, s, f, ws, wf) for s, f in itertools.product(LANES, repeat=2)
       for ws, wf in itertools.product((W_MIN, 3.5, W_MAX), repeat=2)]  # fmt: skip


def test_the_default_structure_reproduces_the_original_networks_exactly():
    """Every coordinate, id and attribute equals the network built before the structure was
    parametrised (fingerprint taken from the pre-change code, both J2 variants)."""
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for lanes in (1, 2):
        got = fingerprint(build_demo_network(lanes))
        for part in ("roads", "connectors", "junctions"):
            bad = [
                k
                for k in expected[str(lanes)][part]
                if got[part].get(k) != expected[str(lanes)][part][k]
            ]
            assert not bad and set(got[part]) == set(expected[str(lanes)][part]), (
                lanes,
                part,
                bad[:5],
            )
        assert got == expected[str(lanes)]
    assert build_demo_network() is build_demo_network(Structure())  # one cached object


@pytest.mark.parametrize(
    "kwargs, text",
    [
        ({"surface_lanes": 0}, "surface_lanes 0 is outside 1..4"),
        ({"flyover_lanes": 5}, "flyover_lanes 5 is outside 1..4"),
        ({"surface_lanes": 2.5}, "surface_lanes 2.5 is outside"),
        ({"j2_minor_lanes": 3}, "j2_minor_lanes 3 is outside 1..2"),
        ({"surface_width_m": 2.4}, "surface_width_m 2.4 m is outside 2.5..4.0 m"),
        ({"flyover_width_m": 4.01}, "flyover_width_m 4.01 m is outside 2.5..4.0 m"),
        ({"flyover_width_m": "wide"}, "is not a number"),
    ],
)
def test_out_of_range_structures_are_errors_with_the_value_named(kwargs, text):
    with pytest.raises(ValueError, match=text.replace(".", r"\.")):
        Structure(**kwargs)


def _lateral_overlaps(net) -> list[str]:
    """Corridor roads of the same level and side must occupy disjoint lateral intervals
    wherever their x ranges overlap (they are straight, y = reference + offsets)."""
    spans = []
    for r in net.roads:
        ref = r.reference
        if abs(ref[0, 1] - ref[-1, 1]) > 1e-9 or abs(ref[0, 0] - ref[-1, 0]) < 1.0:
            continue  # cross streets are not corridor roads
        side = 1.0 if ref[-1, 0] > ref[0, 0] else -1.0  # left of travel is +y eastbound
        width = sum(ln.width_m for ln in r.lanes)
        lo, hi = sorted((side * r.inner_offset_m, side * (r.inner_offset_m + width)))
        x0, x1 = sorted((ref[0, 0], ref[-1, 0]))
        spans.append((r.id, r.level, x0, x1, lo, hi))
    out = []
    for a, b in itertools.combinations(spans, 2):
        along = min(a[3], b[3]) - max(a[2], b[2])
        across = min(a[5], b[5]) - max(a[4], b[4])
        if a[1] == b[1] and along > 1e-6 and across > 1e-9:
            out.append(f"{a[0]} overlaps {b[0]}")
    return out


def _check(st: Structure) -> None:
    net = build_demo_network(st)
    lg = compile_network(net)  # raises if a segment is shorter than the longest vehicle
    conflict_table(net)
    s, f = st.surface_lanes, st.flyover_lanes
    lanes = {r.id: r.n_lanes for r in net.roads}
    assert (lanes["eb_w4"], lanes["wb_w4"]) == (s + f, s + f)
    assert (lanes["eb_surf_w"], lanes["wb_surf_w"]) == (s, s)
    assert lanes["eb_flyover"] == lanes["eb_ramp_up"] == lanes["wb_ramp_dn"] == f
    assert (lanes["eb_e3"], lanes["wb_e3"], lanes["eb_e2"], lanes["wb_in"]) == (f + 1, f + 1, f, f)
    widths = {r.id: {ln.width_m for ln in r.lanes} for r in net.roads}
    assert widths["eb_surf_w"] == {st.surface_width_m} and widths["eb_flyover"] == {
        st.flyover_width_m
    }
    assert widths["eb_e3"] == {st.flyover_width_m} and widths["eb_surf_e"] == {
        min(3.0, st.flyover_width_m)
    }
    assert validate.dropped_lanes(net) == ["eb_e3:0"]  # the lane drop is still one lane
    assert not validate.grade_separation_violations(net)
    assert not validate.clearance_violations(net, DECK_THICKNESS, MIN_CLEARANCE)
    assert not _lateral_overlaps(net)
    for c in net.connectors:  # links join exactly, turns are longer than the longest vehicle
        a, b = net.lane(c.from_lane), net.lane(c.to_lane)
        np.testing.assert_allclose(c.path[0], a.centreline[-1], atol=1e-9)
        np.testing.assert_allclose(c.path[-1], b.centreline[0], atol=1e-9)
    assert lg.length.min() >= 12.0
    rt = RouteTable()
    for o in net.zones:
        for d in net.zones:
            if o.id != d.id:
                assert fastest_route(net, o.id, d.id) is not None
                rt.add(net, lg, o.id, d.id)  # every road of the route has a lane leading on
    assert {tuple(fastest_route(net, "W", "E")) == tuple(r for r in fastest_route(net, "W", "E"))}
    assert any(net.road(r).kind == "flyover" for r in fastest_route(net, "W", "E"))  # still chosen


@pytest.mark.parametrize(
    "st",
    CORNERS,
    ids=lambda s: f"S{s.surface_lanes}F{s.flyover_lanes}-{s.surface_width_m}-{s.flyover_width_m}",
)
def test_every_corner_of_the_allowed_range_builds_routes_and_is_consistent(st):
    _check(st)


def test_the_extremes_are_in_the_corners_tested_above():
    narrow = Structure(2, 1, 1, W_MIN, W_MIN)  # 1 lane per group at the narrowest width
    wide = Structure(2, 4, 4, W_MAX, W_MAX)  # 4 lanes per group at the widest width
    assert narrow in CORNERS and wide in CORNERS and len(ALL) == 144


@pytest.mark.slow
def test_all_144_combinations_of_lanes_and_widths_build_route_and_are_consistent():
    for st in ALL:
        _check(st)
    assert len(ALL) == 4 * 4 * 3 * 3
