"""The shipped built-in experiments: current, internally consistent, and reproducible."""

import pytest
from fastapi.testclient import TestClient

from trafficsim.engine.pairedstats import paired_difference
from trafficsim.engine.runmetrics import METRICS
from trafficsim.server import experiments as ex
from trafficsim.server.app import create_app
from trafficsim.server.compare_jobs import run_one
from trafficsim.server.compare_spec import CompareLimits, run_specs, validate
from trafficsim.server.config import Settings


def docs():
    return {i: ex.stored(i) for i in ex.definitions()}


def test_the_experiments_are_shipped_and_not_stale():
    for exp_id, doc in docs().items():
        assert doc is not None, f"run `python tools/gen_experiments.py` ({exp_id} is missing)"
        assert not ex.is_stale(doc), (
            f"{exp_id} is stale: the model or the metric definitions changed since it was "
            "generated; run `python tools/gen_experiments.py` in backend/ and commit the result"
        )


def test_their_parameters_are_the_ones_fixed_in_advance():
    for doc in docs().values():
        for c in doc["comparisons"]:
            m = c["result"]["meta"]
            assert (m["runs"], m["duration_s"], m["warmup_s"], m["base_seed"]) == (
                10,
                900.0,
                300.0,
                1,
            )
            assert m["seeds"] == list(range(1, 11)) and m["paired_arrivals"] is True


def test_every_stored_interval_is_what_the_paired_t_gives_for_the_stored_runs():
    for doc in docs().values():
        for c in doc["comparisons"]:
            res = c["result"]
            for row in res["metrics"]:
                a = [r["metrics"][row["id"]] for r in res["runs"]["a"]]
                b = [r["metrics"][row["id"]] for r in res["runs"]["b"]]
                again = paired_difference(a, b)
                assert again["diff"] == row["diff"] and again["ci_lo"] == row["ci_lo"]
                assert again["significant"] == row["significant"]
            assert [r["id"] for r in res["metrics"]] == list(METRICS)
            for side in "ab":
                for r in res["runs"][side]:
                    stored = {k: v for k, v in doc["runs"][r["key"]]["metrics"].items()}
                    assert stored.pop("tt_samples_s") is not None
                    assert stored == r["metrics"]  # the result keeps samples only as distributions


def test_the_api_serves_them_instantly():
    app = create_app(Settings(static_dir=None, warm_up=False, compare=CompareLimits(max_runs=10)))
    with TestClient(app) as client:
        listing = {e["id"]: e for e in client.get("/api/experiments").json()}
        assert set(listing) == {"policy_rush", "flyover_rush", "surface_closed"}
        assert all(e["available"] and e["stale"] is False for e in listing.values())
        pol = client.get("/api/experiments/policy_rush").json()
        assert len(pol["comparisons"]) == 3 and pol["stale"] is False
        assert client.get("/api/experiments/nope").status_code == 404
        lim = client.get("/api/compare/limits").json()
        assert lim["runs"] == [3, 5, 10] and lim["default_warmup_s"] == 300.0
        bad = client.post("/api/compare", json={"a": {}, "b": {}, "runs": 4})
        assert bad.status_code == 422 and any(e["path"] == "runs" for e in bad.json()["errors"])


@pytest.mark.slow
def test_a_stored_run_is_reproduced_exactly_by_the_current_engine():
    doc = ex.stored("flyover_rush")
    _, a, b = ex.definitions()["flyover_rush"]["comparisons"][0]
    spec = run_specs(validate(ex.request_for(a, b), CompareLimits()))[0]
    assert spec["key"] in doc["runs"]  # the key the code computes today is the stored one
    assert run_one(spec)["metrics"] == doc["runs"][spec["key"]]["metrics"]
