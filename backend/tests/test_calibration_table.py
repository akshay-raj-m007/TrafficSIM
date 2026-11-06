"""The committed calibration table must be current and equal to a fresh measurement."""

import json

import pytest

from trafficsim.engine import calibration
from trafficsim.engine.scenario import DEFAULT_MIX


def test_committed_calibration_table_is_current(net):
    doc = json.loads(calibration.TABLE_PATH.read_text(encoding="utf-8"))
    assert doc["digest"] == calibration.table_digest(net, DEFAULT_MIX), (
        "the lane graph, vehicle classes or a model constant changed: run "
        "`python tools/gen_calibration.py` and `python tools/gen_freeflow.py` in backend/ "
        "and commit the new tables"
    )
    assert set(doc["junctions"]["J1"]) == {c.id for c in net.connectors if c.junction_id == "J1"}


def test_the_table_is_what_default_scenarios_use(net):
    """Loading from the table must be instant (no 8 s measurement)."""
    import time

    calibration._cache.clear()
    t0 = time.perf_counter()
    sat = calibration.saturation_flows(net, DEFAULT_MIX, "J1")
    assert time.perf_counter() - t0 < 1.0 and len(sat) == 14


@pytest.mark.slow
def test_table_equals_a_fresh_measurement(net):
    doc = json.loads(calibration.TABLE_PATH.read_text(encoding="utf-8"))["junctions"]["J1"]
    fresh = calibration._measure(net, DEFAULT_MIX, "J1")
    for cid, (sat, l1) in fresh.items():
        assert sat == pytest.approx(doc[cid]["sat_flow_veh_h"], rel=1e-6)
        assert l1 == pytest.approx(doc[cid]["startup_lost_s"], abs=1e-5)
