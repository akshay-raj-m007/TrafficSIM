"""Fast sanity checks for the validation helpers (the long ring-road and capacity runs
in this folder are marked ``slow``)."""

import numpy as np
import pytest

from tests.validation.ring import RING_REF_M, equilibrium_speed, ring_network, run_ring
from trafficsim.engine.vehicle import VEHICLE_CLASSES


def test_ring_is_closed_and_has_the_reference_circumference():
    net = ring_network()
    lane = net.lane("ring:0")
    assert lane.length_m == pytest.approx(RING_REF_M, rel=2e-3)
    np.testing.assert_allclose(lane.centreline[0], lane.centreline[-1], atol=1e-9)


def test_equilibrium_speed_inverts_the_idm_gap_formula():
    car = VEHICLE_CLASSES[0]
    v0 = 16.7
    v = equilibrium_speed(car, 25.0, v0)
    gap = (car.s0_m + v * car.T_s) / np.sqrt(1.0 - (v / v0) ** 4)
    assert gap == pytest.approx(25.0, rel=1e-6)


def test_ring_run_in_free_flow_recovers_from_the_disturbance():
    sim, ts, xs, vs, L, v_eq = run_ring(20, 120.0)
    assert vs[0].min() < 0.6 * v_eq  # the disturbed vehicle starts at half speed
    assert vs[ts >= ts[-1] - 20.0].min() > 0.9 * v_eq and sim.emergency_brakings == 0
