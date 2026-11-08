"""Shipped reference tables of the structure settings (data/structures).

A reset to a new lane / width structure used to measure its tables (minutes on the free tier's
0.1 CPU). The tables of the manifest's structures are measured in advance and shipped; the
file names carry the input digest, so these tests fail (naming the tool) as soon as the model or a
network changes, and a hosted instance never has to measure them.
"""

import json

import pytest

from trafficsim.engine import calibration, tablecache
from trafficsim.engine.calibration import DEFAULT_MIX, table_digest
from trafficsim.engine.freeflow import FreeFlowReference, all_keys, input_digest
from trafficsim.engine.lanegraph import compile_network
from trafficsim.network.demo import build_demo_network
from trafficsim.network.structure import Structure

MANIFEST = tablecache.SHIPPED_DIR / "manifest.json"
FIX = "run `python tools/gen_structure_tables.py` in backend/ and commit data/structures"


def _structures() -> list[Structure]:
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [Structure(**e) for e in doc["structures"]]


def test_the_manifest_covers_every_lane_count_and_every_width():
    sts = set(_structures())
    lanes = {(s.surface_lanes, s.flyover_lanes) for s in sts if s.j2_minor_lanes == 2}
    assert len(lanes | {(2, 2)}) == 16  # every lane count of both groups (the default: committed)
    widths = {
        (s.surface_width_m, s.flyover_width_m)
        for s in sts
        if (s.surface_lanes, s.flyover_lanes) == (2, 2)
    }
    assert len(widths | {(3.5, 3.5)}) == 49  # 7 x 7 widths from 2.5 to 4.0 m
    assert {s.j2_minor_lanes for s in sts} == {1, 2}


def test_every_listed_structure_has_both_tables_for_the_current_model():
    missing = []
    for st in _structures():
        net = build_demo_network(st)
        for kind, digest in (
            ("calibration", table_digest(net, DEFAULT_MIX)),
            ("freeflow", input_digest(net, compile_network(net))),
        ):
            if not tablecache.shipped_path(kind, digest).exists():
                missing.append((kind, st))
    assert not missing, f"{len(missing)} shipped tables missing or stale: {FIX}: {missing[:2]}"


@pytest.mark.parametrize(
    "st", [Structure(2, 4, 2, 3.5, 3.5), Structure(1, 3, 3), Structure(2, 2, 2, 3.5, 2.75)]
)
def test_a_shipped_structure_is_read_without_measuring(st, monkeypatch, tmp_path):
    monkeypatch.delenv(tablecache.ENV_VAR, raising=False)  # no writable cache: only the image

    def refuse(*a, **k):
        raise AssertionError("measured a structure whose tables are shipped")

    monkeypatch.setattr(calibration, "_measure", refuse)
    net = build_demo_network(st)
    flows = calibration.saturation_flows(net, DEFAULT_MIX, "J1")
    assert flows and all(v > 0 for v in flows.values())
    ref = FreeFlowReference(net, compile_network(net))
    assert ref.table_used and ref.ready(all_keys(net))


def _doc(**structure) -> dict:
    from trafficsim.server.presets_doc import preset

    doc = preset("default")
    doc["structure"] |= structure
    return doc


def test_a_layout_without_tables_gets_an_estimate_and_a_known_one_does_not(monkeypatch):
    from trafficsim.server import session_build
    from trafficsim.server.live_scenario import from_doc

    monkeypatch.delenv(tablecache.ENV_VAR, raising=False)
    shipped = from_doc(_doc(surface_lanes=4))  # in the manifest
    custom = from_doc(_doc(surface_width_m=3.1))  # not in the grid
    assert session_build.prepare_estimate(shipped) is None
    est = session_build.prepare_estimate(custom)
    assert est is not None and est >= 1  # about this many seconds, shown to the visitor


@pytest.mark.slow
def test_resetting_to_an_unprepared_layout_reports_an_estimate_and_progress(monkeypatch, tmp_path):
    """The visitor sees "preparing this layout, about N s" and the steps, not a frozen screen."""
    import json

    from fastapi.testclient import TestClient

    from tests.ws_util import hello_and_format
    from trafficsim.server.app import create_app
    from trafficsim.server.config import Settings

    monkeypatch.setenv(tablecache.ENV_VAR, str(tmp_path))  # empty cache: nothing measured before
    app = create_app(Settings(max_sessions=1, static_dir=None, tick_hz=50.0, warm_up=False))
    with TestClient(app) as client, client.websocket_connect("/ws/sim") as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "reset", "scenario": _doc(surface_width_m=3.1)}))
        seen = []
        while True:
            msg = ws.receive()
            text = msg.get("text")
            if text is None:
                continue
            m = json.loads(text)
            if m["type"] == "building":
                seen.append(m)
            if m["type"] == "hello":
                break
    assert seen[0]["estimate_s"] and seen[0]["done"] == 0
    assert [m["done"] for m in seen[1:]] == sorted(m["done"] for m in seen[1:])
    assert seen[-1]["done"] == seen[-1]["total"] > 0
