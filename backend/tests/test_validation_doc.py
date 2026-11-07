"""The stored validation results behind the Validation tab (server/validation_doc.py)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from trafficsim.server import validation_doc as vd
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings

ROOT = Path(__file__).resolve().parents[1]
MEASURED = {"ring_waves", "lane_capacity", "stop_line", "j2_left", "j2_right", "webster"}
DOCUMENTED = {"known_j2_right", "known_saturation"}


def test_the_stored_results_exist_and_are_current():
    doc = vd.stored()
    assert doc is not None, "run: python tools/gen_validation.py"
    assert not vd.is_stale(doc), "the engine changed: run python tools/gen_validation.py (~8 min)"
    assert {i["id"] for i in doc["items"]} == MEASURED | DOCUMENTED


def test_every_item_has_a_value_a_reference_a_source_and_a_command_that_exists():
    for item in vd.stored()["items"]:
        assert item["title"] and item["what"] and item["commands"], item["id"]
        assert item["reference"]["text"] and item["reference"]["source"], item["id"]
        if item["id"] in MEASURED:
            h = item["headline"]
            assert h["measured"] and h["reference"] and h["verdict"], item["id"]
        else:
            assert item["kind"] == "documented"
        for cmd in item["commands"]:
            for path in re.findall(r"(?:tests|tools)/[\w/]+\.py", cmd):
                assert (ROOT / path).exists(), f"{item['id']}: {path} does not exist"


def test_measured_values_are_the_ones_the_validation_tests_accept():
    by = {i["id"]: i for i in vd.stored()["items"]}
    wave = [float(x) for x in by["ring_waves"]["headline"]["measured"].split(" and ")]
    assert all(-20.0 <= w <= -10.0 for w in wave)  # tests/validation/test_ring_road.py
    assert 1800 <= int(by["lane_capacity"]["headline"]["measured"]) <= 2400
    cars = int(by["stop_line"]["headline"]["measured"])
    assert 1500 <= cars <= 2000  # tests/validation/test_capacity.py
    assert by["webster"]["headline"]["verdict"] == "agrees"


def test_the_api_serves_the_stored_file():
    app = create_app(Settings(static_dir=None, warm_up=False))
    with TestClient(app) as client:
        body = client.get("/api/validation").json()
    assert body["stale"] is False and len(body["items"]) == len(MEASURED | DOCUMENTED)
