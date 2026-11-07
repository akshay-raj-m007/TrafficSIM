"""Paired-t interval: checked against SciPy and against a hand-worked example."""

import numpy as np
import pytest
from scipy import stats

from trafficsim.engine.pairedstats import paired_difference, t_cdf, t_ppf


@pytest.mark.parametrize("df", [1, 2, 4, 9, 29, 99])
def test_t_quantile_and_cdf_match_scipy(df):
    for q in (0.6, 0.9, 0.975, 0.995):
        assert t_ppf(q, df) == pytest.approx(stats.t.ppf(q, df), rel=1e-9)
    for t in (0.3, 1.0, 2.5, -1.7):
        assert t_cdf(t, df) == pytest.approx(stats.t.cdf(t, df), abs=1e-12)


def test_the_critical_values_of_3_5_and_10_runs():
    got = {n: t_ppf(0.975, n - 1) for n in (3, 5, 10)}  # df = n - 1
    assert got[3] == pytest.approx(4.302653, abs=1e-6)
    assert got[5] == pytest.approx(2.776445, abs=1e-6)
    assert got[10] == pytest.approx(2.262157, abs=1e-6)


def test_hand_worked_example():
    # A = 10, 12, 9; B = 12, 15, 10  ->  d = 2, 3, 1: mean 2, sd 1, se = 1/sqrt(3) = 0.57735
    # CI = 2 +- 4.302653 * 0.57735 = 2 +- 2.48414 = [-0.48414, 4.48414]: it crosses zero.
    r = paired_difference([10.0, 12.0, 9.0], [12.0, 15.0, 10.0])
    assert r["n"] == 3 and r["df"] == 2
    assert r["mean_a"] == pytest.approx(31 / 3) and r["mean_b"] == pytest.approx(37 / 3)
    assert r["diff"] == pytest.approx(2.0) and r["sd"] == pytest.approx(1.0)
    assert r["ci_lo"] == pytest.approx(-0.48414, abs=1e-4)
    assert r["ci_hi"] == pytest.approx(4.48414, abs=1e-4)
    assert r["significant"] is False  # "not significant with 3 runs"
    assert r["p"] == pytest.approx(stats.ttest_rel([12, 15, 10], [10, 12, 9]).pvalue)
    assert r["p"] == pytest.approx(0.0742, abs=1e-4)  # t = 3.464, df = 2


def test_the_interval_equals_scipys_ttest_on_random_data():
    rng = np.random.default_rng(1)
    for n in (3, 5, 10):
        a = rng.normal(50, 8, n)
        b = a + rng.normal(4, 3, n)
        r = paired_difference(list(a), list(b))
        ref = stats.ttest_rel(b, a)
        ci = ref.confidence_interval(0.95)
        assert r["p"] == pytest.approx(ref.pvalue, rel=1e-8)
        assert (r["ci_lo"], r["ci_hi"]) == pytest.approx((ci.low, ci.high), rel=1e-8)
        assert r["significant"] == (ref.pvalue < 0.05)


def test_identical_runs_give_zero_difference_and_a_zero_width_interval():
    r = paired_difference([3.0, 4.0, 5.0], [3.0, 4.0, 5.0])
    assert r["diff"] == 0.0 and r["identical"] and r["ci_lo"] == r["ci_hi"] == 0.0
    assert r["significant"] is False and r["p"] == 1.0


def test_undefined_pairs_are_dropped_from_that_metric_and_counted():
    r = paired_difference([1.0, None, 3.0, 5.0], [2.0, 9.0, None, 7.0])
    assert r["n"] == 2 and r["df"] == 1 and r["diff"] == pytest.approx(1.5)
    assert [p["a"] for p in r["per_seed"]] == [1.0, None, 3.0, 5.0]  # per-seed kept in full
    one = paired_difference([1.0], [2.0])
    assert one["ci_lo"] is None and one["significant"] is None  # no spread, no interval
    assert paired_difference([None], [None])["diff"] is None
    # one side defined, the other never: the defined side still shows its own mean
    half = paired_difference([1.0, 3.0], [None, None])
    assert (
        half["mean_a"] == 2.0 and half["mean_b"] is None and half["diff"] is None and half["n"] == 0
    )


def test_wider_with_fewer_runs():
    a = [10.0, 12.0, 9.0, 11.0, 10.5, 9.5, 12.5, 11.5, 10.0, 11.0]
    b = [x + d for x, d in zip(a, [1, 2, 0, 3, 1, 2, 1, 0, 2, 1], strict=True)]
    w = lambda r: r["ci_hi"] - r["ci_lo"]  # noqa: E731
    assert w(paired_difference(a[:3], b[:3])) > w(paired_difference(a[:5], b[:5]))
