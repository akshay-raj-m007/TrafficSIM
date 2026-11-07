"""A/B comparison service: validation, keys, cache, job cap, repeatability, A vs A."""

import time
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from copy import deepcopy

import pytest

from trafficsim.engine.runmetrics import METRICS
from trafficsim.server.compare_jobs import CompareBusy, CompareManager, RunCache, run_one
from trafficsim.server.compare_spec import CompareError, CompareLimits, pairing, run_key, validate
from trafficsim.server.presets_doc import preset

LIM = CompareLimits(max_runs=10, max_duration_s=1800.0, max_jobs=1, workers=2)


def req(a="default", b="rush_hour", **kw):
    base = {"a": preset(a), "b": preset(b), "runs": 3, "duration_s": 180.0, "warmup_s": 60.0}
    return base | kw


def manager(tmp_path, workers=1, factory=None):
    return CompareManager(
        CompareLimits(workers=workers), RunCache(tmp_path),
        factory or (lambda n: ThreadPoolExecutor(max_workers=n)),
    )  # fmt: skip


def wait(job, timeout=300.0):
    t0 = time.time()
    while job.state == "running" and time.time() - t0 < timeout:
        time.sleep(0.05)
    assert job.state == "done", job.error
    return job


# ---------------------------------------------------------------- validation (fast) ------
@pytest.mark.parametrize(
    "change, path, text",
    [
        ({"runs": 4}, "runs", "must be one of [3, 5, 10]"),
        ({"runs": 10, "duration_s": 3600.0}, "duration_s", "at most 1800 s"),
        ({"duration_s": 100.0, "warmup_s": 100.0}, "warmup_s", "shorter than the duration"),
        ({"warmup_s": -1.0}, "warmup_s", "non-negative multiple"),
        ({"duration_s": 10.05}, "duration_s", "multiple of 0.1"),
        ({"base_seed": -3}, "base_seed", "whole number"),
        ({"surprise": 1}, "surprise", "unknown field"),
    ],
)
def test_invalid_requests_are_errors_with_paths_not_clamped(change, path, text):
    with pytest.raises(CompareError) as e:
        validate(req() | change, LIM)
    assert any(i["path"] == path and text in i["message"] for i in e.value.items), e.value.items


def test_documents_are_validated_with_their_side_in_the_path():
    bad = req()
    bad["b"]["initial"]["mix"]["car"] = 10
    with pytest.raises(CompareError) as e:
        validate(bad, LIM)
    assert any(
        i["path"] == "b.initial.mix" and "exactly 100" in i["message"] for i in e.value.items
    )


def test_a_server_can_restrict_runs_and_duration():
    tight = CompareLimits(max_runs=3, max_duration_s=300.0)
    with pytest.raises(CompareError, match="at most 3 runs"):
        validate(req(runs=5), tight)
    with pytest.raises(CompareError, match="at most 300 s"):
        validate(req(duration_s=600.0), tight)
    assert validate(req(), tight).runs == 3


def test_changing_the_engine_source_digest_changes_the_key_and_the_cache_misses(
    tmp_path, monkeypatch
):
    from trafficsim.server import compare_spec

    doc = preset("default") | {"seed": 1, "duration_s": 180.0}
    cache = RunCache(tmp_path)
    old_key = run_key(doc, 60.0)
    cache.put(old_key, {"key": old_key, "metrics": {}, "cpu_s": 1.0})
    assert cache.get(run_key(doc, 60.0)) is not None  # same code: a hit
    monkeypatch.setattr(compare_spec, "source_digest", lambda: "edited-engine-logic")
    new_key = run_key(doc, 60.0)
    assert new_key != old_key and cache.get(new_key) is None  # changed code: a miss


def test_the_source_digest_normalises_line_endings_and_sees_content(tmp_path):
    from trafficsim.engine import sourcedigest

    assert sourcedigest.source_digest() == sourcedigest.source_digest()
    crlf, lf = bytes([13, 10]), bytes([10])
    for pkg in ("engine", "network"):
        (tmp_path / pkg).mkdir()
    f = tmp_path / "engine" / "a.py"
    (tmp_path / "network" / "b.py").write_bytes(b"y = 2" + lf)
    f.write_bytes(b"x = 1" + lf + b"z = 3" + lf)
    unix = sourcedigest.digest_of(tmp_path)
    f.write_bytes(b"x = 1" + crlf + b"z = 3" + crlf)  # a Windows checkout of the same file
    assert sourcedigest.digest_of(tmp_path) == unix
    f.write_bytes(b"x = 1" + lf + b"z = 4" + lf)  # changed logic
    assert sourcedigest.digest_of(tmp_path) != unix


# -------------------------------------------------------------- keys and pairing (fast) --
def test_run_keys_depend_on_everything_that_determines_a_run_and_not_on_the_name():
    d = preset("default") | {"seed": 1, "duration_s": 180.0}
    k = run_key(d, 60.0)
    assert run_key(d | {"name": "renamed"}, 60.0) == k
    assert run_key(d, 90.0) != k and run_key(d | {"seed": 2}, 60.0) != k
    assert run_key(d | {"duration_s": 200.0}, 60.0) != k
    other = deepcopy(d)
    other["initial"]["policy"] = "max_pressure"
    assert run_key(other, 60.0) != k
    assert run_key(preset("j2_before") | {"seed": 1, "duration_s": 180.0}, 60.0) != k


def test_pairing_says_when_a_and_b_do_not_share_arrivals():
    assert pairing(preset("default"), preset("flyover_closed"))[0] is True
    ok, why = pairing(preset("default"), preset("rush_hour"))
    assert ok is False and "not paired" in why


def test_the_job_cap_answers_busy_instead_of_queueing(tmp_path):
    blocked = lambda n: type("X", (), {"submit": lambda self, fn, spec: Future(),  # noqa: E731
                                       "shutdown": lambda self, **k: None})()  # fmt: skip
    m = manager(tmp_path, factory=blocked)
    job = m.submit(req())
    assert job.state == "running" and job.total == 6
    with pytest.raises(CompareBusy, match="already running"):
        m.submit(req(b="flyover_closed"))


def test_a_failed_run_cannot_exceed_the_job_cap(tmp_path, monkeypatch):
    """One run fails at once, the other runs are already started and keep going: the job is
    'stopping' and still counts against the cap until they have finished."""
    import threading

    from trafficsim.server import compare_jobs

    release = threading.Event()
    calls = []

    def fake_run(spec):
        calls.append(spec["key"])
        if len(calls) == 1:
            raise RuntimeError("boom")
        release.wait(10)  # a run that has started and cannot be cancelled
        return {"key": spec["key"], "metrics": {}, "cpu_s": 0.0}

    monkeypatch.setattr(compare_jobs, "run_one", fake_run)
    m = manager(tmp_path, factory=lambda n: ThreadPoolExecutor(max_workers=4))
    job = m.submit(req())
    t0 = time.time()
    while job.state == "running" and time.time() - t0 < 5:
        time.sleep(0.02)
    assert job.state == "stopping"  # failed, but runs are still executing
    with pytest.raises(CompareBusy, match="already running"):
        m.submit(req(b="flyover_closed"))  # the cap holds
    release.set()
    t0 = time.time()
    while job.state == "stopping" and time.time() - t0 < 10:
        time.sleep(0.02)
    assert job.state == "error" and "boom" in job.error
    assert m.running == 0 and m.submit(req(b="flyover_closed")).state == "running"  # free again


# --------------------------------------------------------------- whole runs (slow) -------
@pytest.mark.slow
def test_the_same_comparison_twice_gives_identical_numbers_and_the_second_is_cached(tmp_path):
    m = manager(tmp_path)
    r = req("default", "flyover_closed")
    first = wait(m.submit(r))
    second = wait(m.submit(r))
    assert first.result["metrics"] == second.result["metrics"]
    assert first.result["runs"] == second.result["runs"]
    assert first.cached == 0 and second.cached == second.total == 6  # nothing re-ran
    assert second.result["meta"]["cost"]["computed_runs"] == 0
    assert first.result["meta"]["paired_arrivals"] is True
    assert {m_["id"] for m_ in first.result["metrics"]} == set(METRICS)
    cost = first.result["meta"]["cost"]
    print(f"\n[compare] {first.total} runs in {cost['wall_s']} s ({cost['cpu_s']} CPU s); "
          f"repeat: all {second.cached} cached")  # fmt: skip


@pytest.mark.slow
def test_a_against_a_gives_zero_difference_on_every_metric(tmp_path):
    job = wait(manager(tmp_path).submit(req("default", "default")))
    for row in job.result["metrics"]:
        if row["n"]:
            assert row["diff"] == 0.0 and row["identical"], row["id"]
            assert row["significant"] is False, row["id"]
    assert job.total == 3  # identical runs are computed once
    assert job.result["meta"]["paired_arrivals"] is True


@pytest.mark.slow
def test_a_process_pool_gives_the_same_numbers_as_running_inline(tmp_path):
    from trafficsim.server.compare_spec import run_specs

    v = validate(req("default", "default", runs=3), LIM)
    spec = run_specs(v)[0]
    inline = run_one(spec)
    pooled = manager(tmp_path / "p", workers=2,
                     factory=lambda n: ProcessPoolExecutor(max_workers=n))  # fmt: skip
    job = wait(pooled.submit(req("default", "default", runs=3)))
    got = next(r for r in job.result["runs"]["a"] if r["seed"] == spec["seed"])
    assert got["metrics"] == inline["metrics"]


@pytest.mark.slow
def test_progress_counts_finished_runs(tmp_path):
    m = manager(tmp_path)
    job = m.submit(req("default", "flyover_closed"))
    seen = {job.done}
    while job.state == "running":
        seen.add(job.done)
        time.sleep(0.2)
    assert job.state == "done" and job.done == job.total == 6
    assert len(seen) >= 3 and max(seen) <= job.total
