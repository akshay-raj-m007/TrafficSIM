"""Signal plans keep their design saturation flows (design decision F2)."""

import pytest

from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import DEMO_DEMAND, scaled
from trafficsim.engine.scenario import Scenario, SetDemand, SetMix, SetPolicy

RUSH = scaled(DEMO_DEMAND, 1.5)

TRUCKS = (("car", 0.3), ("truck_bus", 0.5), ("two_wheeler", 0.1), ("cav", 0.1))


def test_signal_plans_keep_their_design_flows_through_live_mix_and_demand_changes(net):
    """Like a real plan timed for a design mix: live changes do not retime the signals."""
    sim = Simulation(net, Scenario(seed=3, duration_s=60.0, demand=RUSH,
                                   signal_control="max_pressure"))  # fmt: skip
    design = sim.design[0]
    sat, lost, greens = dict(design.sat), dict(design.startup_lost), design.plan.greens_s
    sim.schedule(SetMix(TRUCKS))
    sim.schedule(SetDemand(scaled(DEMO_DEMAND, 2.0)))
    sim.step_n(20)
    assert sim.current_mix == TRUCKS  # the live mix did change
    assert (dict(sim.design[0].sat), dict(sim.design[0].startup_lost)) == (sat, lost)
    assert sim.design[0].plan.greens_s == greens
    sim.schedule(SetPolicy("fixed_webster"))  # a live switch uses the DESIGN plan
    sim.step_n(5)
    assert sim.signals[0].name == "fixed_webster" and sim.signals[0].plan.greens_s == greens
    mp = Simulation(net, Scenario(seed=3, duration_s=60.0, demand=RUSH,
                                  signal_control="max_pressure_threshold"))  # fmt: skip
    mp.schedule(SetMix(TRUCKS))
    mp.step_n(5)
    assert mp.signals[0].lost_per_switch_s == pytest.approx(
        Simulation(net, Scenario(duration_s=10.0, demand=RUSH,
                                 signal_control="max_pressure_threshold")).signals[0].lost_per_switch_s
    )  # fmt: skip


@pytest.mark.slow
def test_a_reset_with_the_new_mix_recomputes_the_design(net):
    default = Simulation(net, Scenario(seed=3, duration_s=10.0, demand=RUSH))
    reset = Simulation(net, Scenario(seed=3, duration_s=10.0, demand=RUSH, vehicle_mix=TRUCKS))
    assert dict(reset.design[0].sat) != dict(default.design[0].sat)  # measured for 50% trucks
    assert reset.design[0].plan.greens_s != default.design[0].plan.greens_s
