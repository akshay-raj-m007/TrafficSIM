"""Scenario JSON: one schema, clear errors, no silent clamping, exact round trip."""

import json
from copy import deepcopy

import pytest

from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import (
    DEFAULT_DEMAND,
    DEFAULT_Y,
    RUSH_SCALE,
    RUSH_TARGET_Y,
    scaled,
)
from trafficsim.network.demo import build_demo_network
from trafficsim.server.presets_doc import PRESET_INFO, all_presets, preset
from trafficsim.server.scenario_doc import ScenarioDoc, ScenarioError, parse, problems, to_engine


def test_every_preset_is_a_valid_document_and_round_trips_through_json():
    for name in PRESET_INFO:
        raw = preset(name)
        assert problems(raw) == []
        again = json.loads(json.dumps(ScenarioDoc.model_validate(raw).model_dump(mode="json")))
        assert again == json.loads(json.dumps(raw))


def test_presets_differ_in_exactly_what_they_say():
    p = all_presets()
    d = p["default"]
    assert p["rush_hour"]["initial"]["demand"] != d["initial"]["demand"]
    assert p["flyover_closed"]["initial"]["flyover_open"] is False
    assert p["j2_before"]["structure"]["j2_minor_lanes"] == 1
    for other in ("flyover_closed", "j2_before"):  # same demand as the default
        assert p[other]["initial"]["demand"] == d["initial"]["demand"]
    n2 = {(r["origin"], r["destination"]): r["veh_per_h"] for r in d["initial"]["demand"]}
    assert n2[("N2", "W")] == 37 and n2[("N2", "E")] == 214  # 0.8 x measured capacities


def test_rush_hour_hits_the_target_critical_flow_ratio():
    net = build_demo_network()
    ys = []
    for demand in (DEFAULT_DEMAND, scaled(DEFAULT_DEMAND, RUSH_SCALE)):
        from trafficsim.engine.scenario import Scenario

        ys.append(Simulation(net, Scenario(duration_s=1.0, demand=demand)).signals[0].plan.Y)
    print(f"\n[rush hour] J1 Y: default {ys[0]:.3f}, rush x{RUSH_SCALE} {ys[1]:.3f}")
    assert ys[0] == pytest.approx(DEFAULT_Y, abs=5e-4)
    assert ys[1] == pytest.approx(RUSH_TARGET_Y, abs=5e-3)


def _bad(mutate):
    raw = preset("default")
    mutate(raw)
    return problems(raw)


@pytest.mark.parametrize(
    "mutate, path, text",
    [
        (
            lambda r: r["initial"]["mix"].update(car=52),
            "initial.mix",
            "shares sum to 97, must be exactly 100",
        ),
        (
            lambda r: r["initial"]["mix"].update(car=-5),
            "initial.mix.car",
            "greater than or equal to 0",
        ),
        (
            lambda r: r["initial"]["demand"][0].update(veh_per_h=-1),
            "initial.demand.0.veh_per_h",
            "greater than or equal to 0",
        ),
        (
            lambda r: r["initial"]["demand"][0].update(destination="W", origin="W"),
            "initial.demand.0",
            "must differ",
        ),
        (
            lambda r: r["initial"]["demand"][0].update(origin="X9"),
            "initial.demand.0.origin",
            "Input should be",
        ),
        (lambda r: r["initial"].update(policy="magic"), "initial.policy", "Input should be"),
        (
            lambda r: r["structure"].update(j2_minor_lanes=3),
            "structure.j2_minor_lanes",
            "j2_minor_lanes 3 is outside 1..2",
        ),
        (
            lambda r: r["structure"].update(surface_lanes=5),
            "structure.surface_lanes",
            "surface_lanes 5 is outside 1..4",
        ),
        (
            lambda r: r["structure"].update(flyover_lanes=0),
            "structure.flyover_lanes",
            "flyover_lanes 0 is outside 1..4",
        ),
        (
            lambda r: r["structure"].update(surface_width_m=2.4),
            "structure.surface_width_m",
            "surface_width_m 2.4 m is outside 2.5..4.0 m",
        ),
        (
            lambda r: r["structure"].update(flyover_width_m=4.5),
            "structure.flyover_width_m",
            "flyover_width_m 4.5 m is outside 2.5..4.0 m",
        ),
        (
            lambda r: r["structure"].pop("flyover_width_m"),
            "structure.flyover_width_m",
            "Field required",
        ),
        (lambda r: r.update(seed=-1), "seed", "greater than or equal to 0"),
        (lambda r: r.update(duration_s=0), "duration_s", "greater than 0"),
        (lambda r: r.update(duration_s=10.05), "(document)", "not a multiple of 0.1 s"),
        (lambda r: r.update(version=2), "version", "Input should be 1"),
        (lambda r: r.update(extra_field=1), "extra_field", "Extra inputs are not permitted"),
        (lambda r: r["initial"].pop("mix"), "initial.mix", "Field required"),
        (
            lambda r: r["changes"].append({"tick": 5, "type": "set_flyover", "open": True}),
            "(document)",
            "already open",
        ),
        (
            lambda r: r["changes"].append({"tick": 99999999, "type": "set_flyover", "open": False}),
            "(document)",
            "after the end",
        ),
    ],
)
def test_invalid_input_gives_a_path_and_a_plain_message(mutate, path, text):
    found = _bad(mutate)
    assert any(p["path"] == path and text in p["message"] for p in found), found


def test_nothing_is_clamped_or_normalised():
    raw = preset("default")
    raw["initial"]["mix"] = {"car": 50.0, "truck_bus": 10.0, "two_wheeler": 30.0, "cav": 5.0}
    with pytest.raises(ScenarioError, match="sum to 95"):
        parse(raw)
    raw["initial"]["mix"]["car"] = 55.0000001  # off by 1e-7 percent: still exact enough
    assert problems(raw) == []
    raw["initial"]["mix"]["car"] = 55.01
    assert problems(raw)


def test_a_document_converts_to_the_engine_scenario_including_its_change_log():
    raw = deepcopy(preset("rush_hour"))
    raw["changes"] = [
        {"tick": 300, "type": "set_flyover", "open": False},
        {"tick": 600, "type": "set_policy", "policy": "max_pressure"},
        {
            "tick": 900,
            "type": "set_mix",
            "mix": {"car": 40, "truck_bus": 20, "two_wheeler": 30, "cav": 10},
        },
        {
            "tick": 1200,
            "type": "set_demand",
            "demand": [{"origin": "W", "destination": "E", "veh_per_h": 500}],
        },
    ]
    sc = to_engine(parse(raw))
    assert [t for t, _ in sc.changes] == [300, 600, 900, 1200]
    assert sc.seed == 42 and sc.signal_control == "fixed_webster" and sc.flyover_open
    sim = Simulation(build_demo_network(), sc)
    sim.step_n(1300)
    assert [t for t, _ in sim.change_log] == [300, 600, 900, 1200]
