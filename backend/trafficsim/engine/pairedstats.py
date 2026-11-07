"""Paired-t confidence interval for the difference of two scenarios over common seeds.

For n paired runs, d_i = B_i - A_i (same seed in A and B), and with the sample mean and
standard deviation (n - 1 in the denominator) of the differences,

    CI = mean(d) +- t(0.975, n - 1) * sd / sqrt(n),      df = n - 1.

So 3, 5 and 10 runs use t = 4.303, 2.776, 2.262. The Student-t quantile is computed here
(regularised incomplete beta, standard library only) so the engine needs no SciPy; the
tests compare it with scipy.stats.t.ppf and with a worked example. Pairs where either
value is undefined (None) are dropped from that metric and ``n`` says how many were used.
"""

from __future__ import annotations

import math

CONFIDENCE = 0.95
_EPS = 1e-14
NO_VARIANCE_REL = 1e-12  # sd below this fraction of |mean| counts as zero variance
_MAX_ITER = 500


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction of the incomplete beta function (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, _MAX_ITER):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            return h
    raise ArithmeticError("incomplete beta did not converge")


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(ln_front + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    p = 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))  # P(T > |t|)
    return 1.0 - p if t > 0 else p


def t_ppf(q: float, df: float) -> float:
    """Quantile of Student's t for 0.5 <= q < 1 (bisection on the CDF)."""
    if not 0.5 <= q < 1.0:
        raise ValueError("q must be in [0.5, 1)")
    lo, hi = 0.0, 1.0
    while t_cdf(hi, df) < q:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _defined_mean(values: list[float | None]) -> float | None:
    got = [x for x in values if x is not None]
    return sum(got) / len(got) if got else None


def paired_difference(a: list[float | None], b: list[float | None]) -> dict:
    """Mean A, mean B, difference B - A and its 95 % paired-t interval (see module doc)."""
    if len(a) != len(b):
        raise ValueError("A and B need the same number of runs")
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    n = len(pairs)
    out: dict = {"n": n, "per_seed": [{"a": x, "b": y} for x, y in zip(a, b, strict=True)]}
    if n == 0:  # no usable pair: each side still shows its own defined values, no difference
        return out | {
            "mean_a": _defined_mean(a), "mean_b": _defined_mean(b), "diff": None,
            "ci_lo": None, "ci_hi": None, "df": None, "t_crit": None, "p": None,
            "significant": None, "identical": None,
        }  # fmt: skip
    d = [y - x for x, y in pairs]
    mean_a, mean_b = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
    mean = sum(d) / n
    out |= {"mean_a": mean_a, "mean_b": mean_b, "diff": mean,
            "identical": all(v == 0.0 for v in d), "constant_difference": False}  # fmt: skip
    if n < 2:  # a single pair has no spread: no interval, never "significant"
        return out | {"ci_lo": None, "ci_hi": None, "df": 0, "t_crit": None, "p": None,
                      "significant": None}  # fmt: skip
    sd = math.sqrt(sum((v - mean) ** 2 for v in d) / (n - 1))
    se = sd / math.sqrt(n)
    df = n - 1
    if sd <= NO_VARIANCE_REL * max(1.0, abs(mean)) and mean != 0.0:
        # Every seed shows the same non-zero difference: no variance, so the t interval has
        # no meaning (it would be a zero-width interval and p = 0). Say so, report no verdict.
        return out | {"sd": 0.0, "se": 0.0, "df": df, "t_crit": None, "ci_lo": None,
                      "ci_hi": None, "p": None, "significant": None,
                      "constant_difference": True}  # fmt: skip
    t_crit = t_ppf(0.5 + CONFIDENCE / 2.0, df)
    lo, hi = mean - t_crit * se, mean + t_crit * se
    # se == 0: all differences are equal, there is no spread to test against
    p = (1.0 if mean == 0.0 else 0.0) if se == 0.0 else 2.0 * (1.0 - t_cdf(abs(mean / se), df))
    return out | {"sd": sd, "se": se, "df": df, "t_crit": t_crit, "ci_lo": lo, "ci_hi": hi,
                  "p": p, "significant": not (lo <= 0.0 <= hi)}  # fmt: skip
