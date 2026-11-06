"""Validation: stop-and-go waves on a single-lane ring road (Sugiyama et al. 2008 style).

Cars only, ~1 km ring, started in exact IDM equilibrium with one vehicle disturbed to
half speed. At low density the disturbance must decay (string stable); at high density
it must grow into stop-and-go waves travelling upstream. Empirically such waves move
against the traffic at about -10 to -20 km/h (e.g. Kerner & Rehborn 1996: ~-15 km/h;
Treiber & Kesting 2013, Ch. 18). All numbers are printed.
"""

import numpy as np
import pytest

from tests.validation.ring import run_ring, wave_speed

DURATION_S = 900.0
MEASURE_FROM_S = 600.0  # last five minutes
EMPIRICAL_WAVE_KMH = (-20.0, -10.0)


pytestmark = pytest.mark.slow  # long simulation runs


@pytest.fixture(scope="module")
def sweep():
    rows = {}
    for rho in (30, 45, 60, 70, 80):
        sim, ts, xs, vs, L, v_eq = run_ring(rho, DURATION_S)
        v = vs[ts >= MEASURE_FROM_S]
        rows[rho] = dict(
            v_eq=v_eq * 3.6,
            mean=v.mean() * 3.6,
            sd=v.std(axis=1).mean() * 3.6,
            vmin=v.min() * 3.6,
            stopped=(v < 0.5).mean(),
            flow=rho * v.mean() * 3.6,
            wave=wave_speed(ts, xs, vs, L, DURATION_S - MEASURE_FROM_S) * 3.6,
            emerg=sim.emergency_brakings,
        )
    print("\n[ring road] cars, 1 km, last 5 of 15 min")
    print(" veh/km  v_eq   mean  sd(veh)  min v  stopped  flow veh/h  wave km/h")
    for rho, r in rows.items():
        print(f" {rho:6d} {r['v_eq']:5.1f} {r['mean']:6.1f} {r['sd']:8.2f} {r['vmin']:6.1f} "
              f"{r['stopped']:7.1%} {r['flow']:10.0f} {r['wave']:10.1f}")  # fmt: skip
    return rows


def test_low_density_is_stable(sweep):
    r = sweep[30]
    assert r["sd"] < 0.5 and r["stopped"] == 0.0


def test_high_density_shows_stop_and_go(sweep):
    for rho in (70, 80):
        r = sweep[rho]
        assert r["vmin"] < 1.0 and r["stopped"] > 0.1 and r["sd"] > 10.0


def test_waves_travel_upstream_at_empirical_speed(sweep):
    lo, hi = EMPIRICAL_WAVE_KMH
    for rho in (70, 80):
        assert lo <= sweep[rho]["wave"] <= hi


def test_no_collisions_or_emergency_braking_in_jams(sweep):
    assert all(r["emerg"] == 0 for r in sweep.values())
    assert np.isfinite([r["wave"] for r in sweep.values()]).all()
