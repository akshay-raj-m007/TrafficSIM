"""Pooled travel-time distributions of a comparison (server/compare_dist.py)."""

import numpy as np

from trafficsim.server.compare_dist import BIN_S, MAX_S, distributions, pooled


def test_histogram_counts_and_box_match_the_samples():
    runs = [[100.0, 105.0, 111.0, 250.0], [99.9, 300.0, 899.9, 950.0]]
    d = pooled(runs)
    allv = np.array([t for r in runs for t in r])
    assert d["n"] == 8 and d["overflow"] == 1 and sum(d["counts"]) == 7
    assert d["counts"][int(105.0 // BIN_S)] == 2  # 100.0 and 105.0 share the 100-110 s bin
    assert len(d["counts"]) == int(MAX_S / BIN_S)
    for name, q in (("q1", 25), ("median", 50), ("q3", 75), ("p90", 90)):
        assert d["box"][name] == float(np.percentile(allv, q))
    assert d["box"]["min"] == 99.9 and d["box"]["max"] == 950.0


def test_no_completed_trip_gives_an_empty_distribution():
    d = pooled([[], []])
    assert d["n"] == 0 and d["box"] is None and sum(d["counts"]) == 0


def test_a_distribution_per_side():
    per = {s: [{"metrics": {"tt_samples_s": [10.0 * (i + 1)]}} for i in range(3)] for s in "ab"}
    out = distributions(per)
    assert set(out) == {"a", "b"} and out["a"]["n"] == 3
