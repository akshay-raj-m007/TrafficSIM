"""What a live session runs, and how it moves between engine objects and JSON documents.

``Setup`` = scenario name + structure (J2 minor approach) + engine scenario. A session is
created from the connection parameters, reset from a scenario document or a preset, and
exported at any moment as a document whose ``changes`` is the log of live changes so far,
so that importing it reproduces the run exactly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from pydantic import TypeAdapter, ValidationError

from trafficsim.engine.scenario import (
    Change,
    Scenario,
    SetDemand,
    SetFlyover,
    SetMix,
    SetPolicy,
)
from trafficsim.network.demo import build_demo_network
from trafficsim.network.structure import Structure as NetStructure
from trafficsim.network.types import Network
from trafficsim.server.presets_doc import preset
from trafficsim.server.scenario_doc import (
    SCHEMA_VERSION,
    ScenarioError,
    change_dict,
    engine_change,
    mix_of,
    parse,
    rows_of,
    to_engine,
)
from trafficsim.server.scenario_doc import (
    Change as ChangeModel,
)
from trafficsim.server.session_config import SessionParams

_change_adapter: TypeAdapter = TypeAdapter(ChangeModel)


@dataclass(frozen=True)
class Setup:
    name: str
    structure: NetStructure
    scenario: Scenario

    @property
    def network(self) -> Network:
        return build_demo_network(self.structure)  # cached per structure

    def folded(self, sim, seed: int | None = None) -> Setup:
        """The settings in force now (the initial ones with every live change applied) as the
        new initial settings, no change log, optionally a new seed. This is what a reset keeps."""
        sc = self.scenario
        demand, mix, policy, flyover = sc.demand, sc.vehicle_mix, sc.signal_control, sc.flyover_open
        for _, c in sim.all_changes:
            if isinstance(c, SetDemand):
                demand = c.flows
            elif isinstance(c, SetMix):
                mix = c.mix
            elif isinstance(c, SetPolicy):
                policy = c.policy
            elif isinstance(c, SetFlyover):
                flyover = c.open
        new = replace(
            sc, seed=sc.seed if seed is None else seed, demand=demand, vehicle_mix=mix,
            signal_control=policy, flyover_open=flyover, changes=(),
        )  # fmt: skip
        return replace(self, scenario=new)


def from_params(p: SessionParams) -> Setup:
    return Setup("Default", NetStructure(), p.scenario())


def from_doc(raw) -> Setup:
    doc = parse(raw)
    return Setup(doc.name, doc.structure.to_network(), to_engine(doc))


def from_preset(name: str, seed: int | None = None) -> Setup:
    raw = preset(name)
    if seed is not None:
        raw["seed"] = seed
    return from_doc(raw)


def live_change(raw: dict, tick: int) -> Change:
    """A client's change (no tick) validated against the schema; ScenarioError if invalid."""
    if not isinstance(raw, dict):
        raise ScenarioError([{"path": "change", "message": "must be an object"}])
    try:
        model = _change_adapter.validate_python({**raw, "tick": tick})
    except ValidationError as exc:
        items = [
            {
                "path": ".".join(str(x) for x in e["loc"][1:]) or "change",
                "message": str(e["msg"]).removeprefix("Value error, "),
            }
            for e in exc.errors(include_url=False, include_context=False, include_input=False)
        ]
        raise ScenarioError(items) from exc
    return engine_change(model)


def export_doc(setup: Setup, sim) -> dict:
    """The session as a scenario document; ``changes`` = every live change so far."""
    sc = setup.scenario
    if sc.signal_control == "uncontrolled":
        raise ScenarioError(
            [{"path": "initial.policy", "message": "uncontrolled is an experiment mode"}]
        )
    doc = {
        "version": SCHEMA_VERSION,
        "name": setup.name,
        "seed": sc.seed,
        "duration_s": sc.duration_s,
        "structure": asdict(setup.structure),
        "initial": {
            "demand": rows_of(sc.demand),
            "mix": mix_of(sc.vehicle_mix),
            "policy": sc.signal_control,
            "flyover_open": sc.flyover_open,
        },
        "changes": [change_dict(t, c) for t, c in sim.all_changes],
    }
    parse(doc)  # an export must always be importable
    return doc
