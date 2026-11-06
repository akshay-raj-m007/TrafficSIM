"""Invariant 3 — Spillback guard: no vehicle enters a junction unless the exit lane has
room for it.

Decision check: at the moment each vehicle committed to entering (its last chance to
stop comfortably), the guaranteed room on its exit lane was >= its length + s0.
Outcome check: no vehicle is ever held up inside a junction box. The blocked-exit case
(closed N1 exit) is in tests/engine/test_junctions.py::test_spillback_guard_with_blocked_exit.
"""

import math

import pytest

pytestmark = pytest.mark.slow  # long simulation runs


@pytest.mark.parametrize("run", ["medium", "overload"])
def test_every_entry_had_room_and_no_box_blocking(request, run):
    rep = request.getfixturevalue(run)
    sim = rep.sim
    e = sim.log.junction_entries
    short = [x for x in e if not x.room >= x.need]
    unknown = [x for x in e if math.isnan(x.room)]
    later = sum(x.room_at_entry < x.need for x in e)
    print(f"\n[spillback:{run}] {len(e)} junction entries; room < need at commitment: "
          f"{len(short)}; uncommitted entries: {len(unknown)}; room shrank below need "
          f"between commitment and line crossing (diagnostic): {later}; vehicle-seconds "
          f"held inside junction boxes {sim.box_stopped_vehicle_s:.1f}")  # fmt: skip
    assert e and not short and not unknown
    assert sim.box_stopped_vehicle_s == 0.0
