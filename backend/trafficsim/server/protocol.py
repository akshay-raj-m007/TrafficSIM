"""WebSocket message schemas.

Client -> server (JSON, validated with pydantic): set_speed, reset (seed / preset / scenario
document), apply (a live change), export, charts (on / off), inspect (a vehicle or null), ping.
Server -> client:
  * binary frames: vehicle poses, see ``frames.py`` (sent only when the simulation advanced)
  * JSON ``hello`` (session description, vehicle class dimensions, frame format),
    ``kpi`` (measured KPIs, at most once per wall second), ``stats`` (streaming/server
    measurements, once per wall second), ``applied`` / ``rejected`` (answer to ``apply``
    and to an invalid ``reset``), ``scenario`` (answer to ``export``), ``busy``, ``pong``,
    ``error``, ``charts`` (only while asked for: MFD points, corridor speed columns and queue
    samples not yet sent, see engine/charts.py), ``vehicle`` (the selected vehicle, with every
    frame until it leaves; see inspector.py).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

from trafficsim.engine.constants import STEPS_PER_SECOND
from trafficsim.engine.kpi import KPI_DEFS
from trafficsim.engine.vehicle import VEHICLE_CLASSES
from trafficsim.server.frames import LC_BLEND_S, FrameFormat

# Simulated seconds per wall-clock second. 0 pauses. The binary frame header carries the
# index into this list.
ALLOWED_SPEEDS: tuple[float, ...] = (0, 0.25, 0.5, 1, 2, 5, 10)


class SetSpeed(BaseModel):
    type: Literal["set_speed"]
    speed: float

    @field_validator("speed")
    @classmethod
    def _allowed(cls, v: float) -> float:
        if v not in ALLOWED_SPEEDS:
            raise ValueError(f"speed must be one of {ALLOWED_SPEEDS}")
        return v


class Reset(BaseModel):
    """seed only: same settings, new seed; preset: a named preset (optionally with a seed);
    scenario: a whole scenario document (import). At most one of preset / scenario."""

    type: Literal["reset"]
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    preset: str | None = None
    scenario: dict | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Reset:
        if self.preset is not None and self.scenario is not None:
            raise ValueError("give a preset or a scenario, not both")
        if self.scenario is not None and self.seed is not None:
            raise ValueError("the scenario document carries its own seed")
        return self


class Apply(BaseModel):
    """A live change (see scenario_doc.py for the fields; the tick is set by the server)."""

    type: Literal["apply"]
    change: dict


class Export(BaseModel):
    type: Literal["export"]


class Charts(BaseModel):
    """Start / stop the 1 Hz ``charts`` stream (the first message carries the whole history)."""

    type: Literal["charts"]
    on: bool


class Inspect(BaseModel):
    """Select a vehicle (frame id) for the ``vehicle`` stream, or null to stop it."""

    type: Literal["inspect"]
    id: int | None = Field(default=None, ge=0, le=0xFFFF)


class Activity(BaseModel):
    """The visitor is there (mouse, keys, touch); sent by the page at most every 20 s."""

    type: Literal["activity"]


class Ping(BaseModel):
    type: Literal["ping"]
    id: int


ClientMsg = SetSpeed | Reset | Apply | Export | Charts | Inspect | Activity | Ping
ClientMessage = Annotated[ClientMsg, Field(discriminator="type")]
_client_adapter: TypeAdapter[ClientMsg] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str) -> ClientMsg:
    """Raises pydantic.ValidationError on malformed input."""
    return _client_adapter.validate_json(raw)


def speed_index(speed: float) -> int:
    return ALLOWED_SPEEDS.index(speed)


def hello(
    session_id: str, dt: float, tick_hz: float, sc, demand_scale: float, epoch: int,
    fmt: FrameFormat, segments: list[dict], scenario: dict | None = None,
    structure: dict | None = None,
) -> dict:  # fmt: skip
    return {
        "type": "hello",
        "session_id": session_id,
        "dt": dt,
        "steps_per_second": STEPS_PER_SECOND,
        "tick_hz": tick_hz,
        "speeds": list(ALLOWED_SPEEDS),
        "seed": sc.seed,
        "signal": sc.signal_control,
        "demand_scale": demand_scale,  # query-parameter experiment seam only
        "duration_s": sc.duration_s,
        "epoch": epoch & 255,
        "classes": [
            {"name": c.name, "length_m": c.length_m, "width_m": c.width_m, "height_m": c.height_m}
            for c in VEHICLE_CLASSES
        ],
        "frame": fmt.to_dict(),
        "scenario": scenario,  # the document in force (None if it cannot be exported)
        "network": structure or {},  # the structure: fetch /api/network with it as the query
        "segments": segments,  # frame segment index -> lane / connector id, length, successors
        "lane_change_blend_s": LC_BLEND_S,
        "kpi_defs": KPI_DEFS,
    }


def kpi(snapshot: dict) -> dict:
    return {"type": "kpi", **snapshot}


def stats(t: float, tick: int, speed: float, done: bool, lag_ms: float, agg: dict) -> dict:
    return {
        "type": "stats", "t": t, "tick": tick, "speed": speed, "done": done,
        "lag_ms": round(lag_ms, 1),  # how late the frame left versus its schedule
        **agg,
    }  # fmt: skip


def busy(max_sessions: int) -> dict:
    return {
        "type": "busy",
        "sessions_max": max_sessions,
        "message": (
            f"The free server allows {max_sessions} live simulations at a time and both are in "
            "use. Try again in a minute: this page retries by itself. The precomputed Compare "
            "and Validation results work meanwhile."
        ),
    }


def idle(minutes: float) -> dict:
    return {
        "type": "idle",
        "message": f"Paused after {minutes:g} minutes without activity. Click to resume "
        "(this starts a new run).",
    }


def charts(since: dict) -> dict:
    return {"type": "charts", **since}


def pong(ping_id: int) -> dict:
    return {"type": "pong", "id": ping_id}


def error(message: str, detail: Any = None) -> dict:
    return {"type": "error", "message": message, "detail": detail}


def building(reason: str, name: str) -> dict:
    """A scenario is being built (off the event loop); the hello follows when it is ready."""
    return {"type": "building", "reason": reason, "name": name}


def applied(tick: int, change: dict) -> dict:
    return {"type": "applied", "tick": tick, "change": change}


def rejected(what: str, errors: list[dict]) -> dict:
    """``what`` names the request that failed ("apply" or "reset"); nothing was changed."""
    return {"type": "rejected", "request": what, "errors": errors}


def scenario_doc(doc: dict) -> dict:
    return {"type": "scenario", "scenario": doc}
