"""The on-disk cache of measured tables: the same mix is never measured twice."""

import time

import pytest

from trafficsim.engine import calibration, tablecache

TRUCKS = (("car", 0.3), ("truck_bus", 0.5), ("two_wheeler", 0.1), ("cav", 0.1))


def test_store_load_round_trip_and_digest_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv(tablecache.ENV_VAR, str(tmp_path))
    assert tablecache.load("calibration", "abc") is None
    tablecache.store("calibration", "abc", {"digest": "abc", "x": 1})
    assert tablecache.load("calibration", "abc") == {"digest": "abc", "x": 1}
    assert tablecache.load("freeflow", "abc") is None  # kinds are separate
    (tmp_path / f"calibration-{'d' * 40}.json").write_text('{"digest": "other"}')
    assert tablecache.load("calibration", "d" * 40) is None  # content must match the digest
    (tmp_path / f"calibration-{'e' * 40}.json").write_text("{torn")
    assert tablecache.load("calibration", "e" * 40) is None  # unreadable = miss, not a crash


def test_without_a_cache_directory_nothing_is_stored(monkeypatch):
    monkeypatch.delenv(tablecache.ENV_VAR, raising=False)
    tablecache.store("calibration", "abc", {"digest": "abc"})
    assert tablecache.load("calibration", "abc") is None


@pytest.mark.slow
def test_a_non_default_mix_is_measured_once_then_read_from_disk(net, tmp_path, monkeypatch):
    monkeypatch.setenv(tablecache.ENV_VAR, str(tmp_path))
    calibration._cache.clear()
    t0 = time.perf_counter()
    first = calibration.saturation_flows(net, TRUCKS, "J1")
    measured_s = time.perf_counter() - t0
    assert measured_s > 2.0 and list(tmp_path.glob("calibration-*.json"))

    calibration._cache.clear()  # a new process / session: nothing in memory
    monkeypatch.setattr(calibration, "_measure", lambda *a: pytest.fail("measured twice"))
    t0 = time.perf_counter()
    again = calibration.saturation_flows(net, TRUCKS, "J1")
    cached_s = time.perf_counter() - t0
    assert again == first and cached_s < 1.0
    default = calibration.saturation_flows(net, calibration.DEFAULT_MIX, "J1")
    assert default != first  # the key includes the mix: the default is a different table
    print(f"\n[table cache] 50% trucks mix: measured in {measured_s:.1f} s, "
          f"from the cache in {cached_s * 1000:.0f} ms")  # fmt: skip
