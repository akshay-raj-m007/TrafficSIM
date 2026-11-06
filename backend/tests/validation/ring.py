"""Single-lane ring road experiment (Sugiyama-style) for validation tests."""

from __future__ import annotations

import numpy as np

from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import CLASS_INDEX, VEHICLE_CLASSES
from trafficsim.network.builder import NetworkBuilder

RING_REF_M = 1000.0  # circumference of the reference circle [m]
LAPS = 400  # route length in laps (more than any test can drive)
LIMIT_KMH = 100.0  # above the car's v0, so the class desired speed governs


def ring_network(circumference: float = RING_REF_M):
    r = circumference / (2 * np.pi)
    th = np.linspace(0.0, 2 * np.pi, 361)
    ref = np.column_stack([r * np.cos(th), r * np.sin(th), np.zeros_like(th)])
    ref[-1] = ref[0]  # closed exactly
    b = NetworkBuilder()
    b.road("ring", "surface", ref, [3.5], -1.75, LIMIT_KMH)  # centreline = the circle
    b.link("ring", 0, "ring", 0)
    b.zone("R", "ring", "ring")
    return b.build()


def equilibrium_speed(cls, gap: float, v0: float) -> float:
    """IDM steady state: gap = (s0 + v T) / sqrt(1 - (v/v0)^4), solved by bisection."""
    lo, hi = 0.0, v0
    for _ in range(80):
        v = 0.5 * (lo + hi)
        x = v / v0
        need = (cls.s0_m + v * cls.T_s) / np.sqrt(1.0 - x * x * x * x)
        lo, hi = (v, hi) if need < gap else (lo, v)
    return 0.5 * (lo + hi)


def run_ring(density_per_km: float, duration_s: float, seed: int = 1, cls_name: str = "car"):
    """Returns (sim, times, positions [n_t, n_veh] unwrapped arc length, speeds)."""
    net = ring_network()
    sim = Simulation(net, Scenario(seed=seed, duration_s=duration_s, signal_control="uncontrolled"))
    lg = sim.lg
    route = sim.routes.add_explicit(lg, ("ring",) * LAPS, ("ring", "ring"))
    L = float(lg.length[0])
    n = max(2, round(density_per_km * L / 1000.0))
    cls = VEHICLE_CLASSES[CLASS_INDEX[cls_name]]
    v0 = float(lg.v0_eff[0, CLASS_INDEX[cls_name]])
    spacing = L / n
    v_eq = equilibrium_speed(cls, spacing - cls.length_m, v0)
    for k in range(n):
        v = v_eq * (0.5 if k == 0 else 1.0)  # one disturbed vehicle
        sim.demand.place(
            sim.vehicles, route, CLASS_INDEX[cls_name], 0, (n - k) * spacing - 1e-6, v, 0.0
        )
    order = np.argsort(sim.vehicles.vid)
    ts, xs, vs_ = [], [], []
    while not sim.done:
        sim.step()
        v = sim.vehicles
        o = np.argsort(v.vid)
        ts.append(sim.time_s)
        xs.append(v.rpos[o] * L + v.s[o])
        vs_.append(v.v[o].copy())
    del order
    return sim, np.array(ts), np.array(xs), np.array(vs_), L, v_eq


def wave_speed(ts, xs, vs_, L, window_s: float, lag_s: float = 5.0, bin_m: float = 5.0):
    """Propagation speed [m/s] of speed patterns on the ring (negative = upstream).

    The speed field V(x, t) is interpolated (periodically) between vehicles onto bins of
    ``bin_m``; for each pair of frames ``lag_s`` apart the circular cross-correlation of
    the field is maximised over spatial shifts; the median shift / lag is returned.
    Robust to several coexisting jams (unlike tracking the slowest vehicle).
    """
    dt = ts[1] - ts[0]
    lag = max(1, round(lag_s / dt))
    grid = np.arange(0.0, L, bin_m)
    nb = grid.size
    sel = np.flatnonzero(ts >= ts[-1] - window_s)

    def field(k):
        x = xs[k] % L
        o = np.argsort(x)
        return np.interp(grid, x[o], vs_[k][o], period=L)

    shifts = []
    for k in sel[:-lag:lag]:
        a, b = field(k), field(k + lag)
        a, b = a - a.mean(), b - b.mean()
        if a.std() < 1e-6:
            continue
        corr = np.fft.ifft(np.fft.fft(b) * np.conj(np.fft.fft(a))).real
        m = int(np.argmax(corr))
        shifts.append((m if m <= nb // 2 else m - nb) * bin_m / (lag * dt))
    return float(np.median(shifts)) if shifts else float("nan")
