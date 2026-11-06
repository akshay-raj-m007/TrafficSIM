"""Scenario runs shared by the invariant tests (each run once per test session)."""

import pytest

from tests.invariants.harness import run_checked
from trafficsim.engine.presets import DEMO_DEMAND, scaled
from trafficsim.engine.scenario import Scenario

RUN_S = 600.0  # simulated seconds per checked run
STEPS = int(RUN_S * 10)


@pytest.fixture(scope="session")
def medium(net):
    """Demo demand, fixed-time Webster signals."""
    return run_checked(net, Scenario(seed=5, duration_s=RUN_S, demand=DEMO_DEMAND), STEPS)


@pytest.fixture(scope="session")
def overload(net):
    """Twice the demo demand (beyond capacity at several places), max-pressure."""
    sc = Scenario(seed=6, duration_s=RUN_S, demand=scaled(DEMO_DEMAND, 2.0),
                  signal_control="max_pressure")  # fmt: skip
    return run_checked(net, sc, STEPS)
