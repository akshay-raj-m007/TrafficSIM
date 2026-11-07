"""The scenario as one validated JSON document (schema version 1).

    {"version": 1, "name": "...", "seed": 42, "duration_s": 900,
     "structure": {"j2_minor_lanes": 2},
     "initial": {"demand": [{"origin": "W", "destination": "E", "veh_per_h": 1100}, ...],
                 "mix": {"car": 55, "truck_bus": 10, "two_wheeler": 30, "cav": 5},
                 "policy": "fixed_webster", "flyover_open": true},
     "changes": [{"tick": 3000, "type": "set_flyover", "open": false}, ...]}

Mix shares are percent and must add up to exactly 100. Nothing is clamped, defaulted or
renormalised: invalid input produces one error per problem with the field path
(``problems(...)``), unknown fields are rejected. ``changes`` is the log of live changes
(tick = the tick a change was applied at): same seed + same document reproduces the run.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from trafficsim.engine.constants import DT
from trafficsim.engine.scenario import (
    DEFAULT_MIX,
    OdFlow,
    Scenario,
    SetDemand,
    SetFlyover,
    SetMix,
    SetPolicy,
)

SCHEMA_VERSION = 1
CLASSES = tuple(n for n, _ in DEFAULT_MIX)
ZONES = ("W", "E", "N1", "S1", "N2")
POLICIES = ("fixed_webster", "max_pressure", "max_pressure_threshold")
MAX_SEED = 2**32 - 1
MIX_SUM_TOL = 1e-6  # percent
MAX_CHANGES = 500  # live changes in one document (matches Settings.max_live_changes)
MAX_DEMAND_ROWS = 100


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemandRow(_Strict):
    origin: Literal["W", "E", "N1", "S1", "N2"]
    destination: Literal["W", "E", "N1", "S1", "N2"]
    veh_per_h: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _distinct(self) -> DemandRow:
        if self.origin == self.destination:
            raise ValueError(f"origin and destination must differ (both {self.origin})")
        return self


class Mix(_Strict):
    """Vehicle-class shares in percent."""

    car: float = Field(ge=0, le=100)
    truck_bus: float = Field(ge=0, le=100)
    two_wheeler: float = Field(ge=0, le=100)
    cav: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _sums_to_100(self) -> Mix:
        total = self.car + self.truck_bus + self.two_wheeler + self.cav
        if abs(total - 100.0) > MIX_SUM_TOL:
            raise ValueError(f"shares sum to {total:g}, must be exactly 100")
        return self

    def to_engine(self) -> tuple[tuple[str, float], ...]:
        return tuple((n, getattr(self, n) / 100.0) for n in CLASSES)


class Structure(_Strict):
    """Settings that only apply on reset (they change the network)."""

    j2_minor_lanes: Literal[1, 2] = 2  # 1 shared lane or 2 turn lanes


class Initial(_Strict):
    demand: list[DemandRow] = Field(max_length=MAX_DEMAND_ROWS)
    mix: Mix
    policy: Literal["fixed_webster", "max_pressure", "max_pressure_threshold"]
    flyover_open: bool


class _At(_Strict):
    tick: int = Field(ge=0)


class SetDemandChange(_At):
    type: Literal["set_demand"]
    demand: list[DemandRow] = Field(max_length=MAX_DEMAND_ROWS)


class SetMixChange(_At):
    type: Literal["set_mix"]
    mix: Mix


class SetPolicyChange(_At):
    type: Literal["set_policy"]
    policy: Literal["fixed_webster", "max_pressure", "max_pressure_threshold"]


class SetFlyoverChange(_At):
    type: Literal["set_flyover"]
    open: bool


Change = Annotated[
    SetDemandChange | SetMixChange | SetPolicyChange | SetFlyoverChange, Field(discriminator="type")
]


class ScenarioDoc(_Strict):
    version: Literal[1]
    name: str = Field(min_length=1, max_length=80)
    seed: int = Field(ge=0, le=MAX_SEED)
    duration_s: float = Field(gt=0, allow_inf_nan=False)
    structure: Structure
    initial: Initial
    changes: list[Change] = Field(default=[], max_length=MAX_CHANGES)

    @model_validator(mode="after")
    def _checks(self) -> ScenarioDoc:
        if abs(self.duration_s / DT - round(self.duration_s / DT)) > 1e-6:
            raise ValueError(f"duration_s {self.duration_s:g} is not a multiple of {DT} s")
        ticks = [c.tick for c in self.changes]
        if ticks != sorted(ticks):
            raise ValueError("changes must be in non-decreasing tick order")
        if ticks and ticks[-1] > self.duration_s / DT:
            raise ValueError(f"change at tick {ticks[-1]} is after the end of the run")
        flyover = self.initial.flyover_open
        for k, c in enumerate(self.changes):
            if isinstance(c, SetFlyoverChange):
                if c.open == flyover:
                    state = "open" if flyover else "closed"
                    raise ValueError(f"changes[{k}]: the flyover is already {state} at that point")
                flyover = c.open
        return self


def problems(raw: Any) -> list[dict[str, str]]:
    """Every problem of a raw document as ``{"path", "message"}`` (empty if valid)."""
    try:
        ScenarioDoc.model_validate(raw)
    except ValidationError as exc:
        out = []
        for e in exc.errors(include_url=False, include_context=False, include_input=False):
            path = ".".join(str(p) for p in e["loc"]) or "(document)"
            msg = str(e["msg"]).removeprefix("Value error, ")
            out.append({"path": path, "message": msg})
        return out
    return []


def parse(raw: Any) -> ScenarioDoc:
    if p := problems(raw):
        raise ScenarioError(p)
    return ScenarioDoc.model_validate(raw)


class ScenarioError(ValueError):
    def __init__(self, items: list[dict[str, str]]) -> None:
        self.items = items
        super().__init__("; ".join(f"{i['path']}: {i['message']}" for i in items))


# ------------------------------------------------------------------ to / from engine -----
def _flows(rows: list[DemandRow]) -> tuple[OdFlow, ...]:
    return tuple(OdFlow(r.origin, r.destination, r.veh_per_h) for r in rows)


def engine_change(c):
    """The engine change of a validated change model."""
    if isinstance(c, SetDemandChange):
        return SetDemand(_flows(c.demand))
    if isinstance(c, SetMixChange):
        return SetMix(c.mix.to_engine())
    if isinstance(c, SetPolicyChange):
        return SetPolicy(c.policy)
    return SetFlyover(c.open)


def to_engine(doc: ScenarioDoc) -> Scenario:
    """The engine scenario (including the change log to replay) of a valid document."""
    changes = [(c.tick, engine_change(c)) for c in doc.changes]
    return Scenario(
        seed=doc.seed, duration_s=doc.duration_s, demand=_flows(doc.initial.demand),
        vehicle_mix=doc.initial.mix.to_engine(), signal_control=doc.initial.policy,
        flyover_open=doc.initial.flyover_open, changes=tuple(changes),
    )  # fmt: skip


def rows_of(flows: tuple[OdFlow, ...]) -> list[dict]:
    return [{"origin": f.origin, "destination": f.destination, "veh_per_h": f.veh_per_h}
            for f in flows]  # fmt: skip


def mix_of(mix: tuple[tuple[str, float], ...]) -> dict[str, float]:
    return {n: round(p * 100.0, 9) for n, p in mix}


def change_dict(tick: int, ch) -> dict:
    if isinstance(ch, SetDemand):
        return {"tick": tick, "type": "set_demand", "demand": rows_of(ch.flows)}
    if isinstance(ch, SetMix):
        return {"tick": tick, "type": "set_mix", "mix": mix_of(ch.mix)}
    if isinstance(ch, SetPolicy):
        return {"tick": tick, "type": "set_policy", "policy": ch.policy}
    return {"tick": tick, "type": "set_flyover", "open": ch.open}
