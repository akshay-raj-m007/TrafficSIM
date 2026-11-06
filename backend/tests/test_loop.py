import pytest

from trafficsim.engine.constants import DT, STEPS_PER_SECOND, ticks_for, time_of
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import OdFlow, Scenario


def test_dt_is_fixed_at_100_ms():
    assert DT == 0.1
    assert STEPS_PER_SECOND == 10
    assert Simulation.dt == DT
    assert "dt" not in Scenario.__dataclass_fields__


def test_single_step_advances_one_tick(net):
    sim = Simulation(net, Scenario(seed=1, duration_s=10.0))
    assert (sim.tick, sim.time_s) == (0, 0.0)
    assert sim.step() is True
    assert (sim.tick, sim.time_s) == (1, 0.1)


def test_clock_is_exact_with_no_float_drift(net):
    sim = Simulation(net, Scenario(duration_s=3600.0))
    sim.step_n(3)
    assert sim.time_s == 0.3  # naive accumulation would give 0.30000000000000004
    sim.step_n(36000 - 3)
    assert sim.tick == 36000
    assert sim.time_s == 3600.0


def test_every_tick_maps_to_exact_decimal_time():
    for tick in range(0, 5000):
        assert time_of(tick) == float(f"{tick / 10:.1f}")


def test_run_until_and_end_of_scenario(net):
    sim = Simulation(net, Scenario(duration_s=5.0))
    assert sim.run_until(2.5) == 25
    assert sim.time_s == 2.5
    assert sim.step_n(1000) == 25  # stops at the scenario end
    assert sim.done and sim.tick == 50
    assert sim.step() is False and sim.tick == 50


def test_step_n_rejects_negative(net):
    with pytest.raises(ValueError):
        Simulation(net, Scenario(duration_s=1.0)).step_n(-1)


def test_two_runs_with_same_seed_are_identical(net):
    a = Simulation(net, Scenario(seed=11, duration_s=60.0))
    b = Simulation(net, Scenario(seed=11, duration_s=60.0))
    a.step_n(600)
    b.step_n(600)
    assert (a.tick, a.time_s) == (b.tick, b.time_s)
    assert a.rng.state_fingerprint() == b.rng.state_fingerprint()


@pytest.mark.parametrize("bad", [0.05, 1.234, -1.0])
def test_duration_must_be_multiple_of_dt(bad):
    with pytest.raises(ValueError):
        ticks_for(bad)


def test_scenario_validation():
    with pytest.raises(ValueError):
        Scenario(vehicle_mix=(("car", 0.5), ("truck_bus", 0.2)))  # sums to 0.7
    with pytest.raises(ValueError):
        Scenario(vehicle_mix=(("hovercraft", 1.0),))
    with pytest.raises(ValueError):
        Scenario(signal_control="random")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        OdFlow("W", "W", 100)
    with pytest.raises(ValueError):
        OdFlow("W", "E", -5)
