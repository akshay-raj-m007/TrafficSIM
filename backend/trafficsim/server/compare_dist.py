"""Travel-time distributions of a comparison, pooled over the runs of one side.

Each run reports the travel times of its completed cohort trips (``tt_samples_s``, 0.1 s
resolution, engine/runmetrics.py). Here they are pooled per side into a histogram with fixed
bins and box-plot statistics, computed once on the backend so the browser only draws them.
Completed trips only: trips still under way at the end are not in it (survivorship), which
matters most when many trips do not finish (README, "A/B comparison").
"""

from __future__ import annotations

import numpy as np

BIN_S = 10.0  # histogram bin width [s]
MAX_S = 900.0  # last bin edge: the run length; slower trips fall in the overflow count
BOX_QUANTILES = (("q1", 25.0), ("median", 50.0), ("q3", 75.0), ("p90", 90.0))


def pooled(samples_per_run: list[list[float]]) -> dict:
    """Histogram counts per bin, overflow count and box statistics of the pooled samples."""
    x = np.array([t for run in samples_per_run for t in run], dtype=np.float64)
    edges = np.arange(0.0, MAX_S + BIN_S, BIN_S)
    counts, _ = np.histogram(x[x < MAX_S], bins=edges)
    out: dict = {
        "n": int(x.size), "bin_s": BIN_S, "counts": counts.tolist(),
        "overflow": int(np.count_nonzero(x >= MAX_S)), "box": None,
    }  # fmt: skip
    if x.size:
        out["box"] = {"min": float(x.min()), "max": float(x.max())} | {
            name: float(np.percentile(x, q)) for name, q in BOX_QUANTILES
        }
    return out


def distributions(per_side: dict[str, list[dict]]) -> dict[str, dict]:
    return {s: pooled([r["metrics"]["tt_samples_s"] for r in runs]) for s, runs in per_side.items()}
