"""WebSocket message schemas.

Client -> server (JSON, validated with pydantic): set_speed, reset, ping.
Server -> client:
  * binary frames: vehicle poses, see ``frames.py`` (sent only when the simulation advanced)
  * JSON ``hello`` (session description, vehicle class dimensions, frame format),
    ``kpi`` (measured KPIs, at most once per wall second), ``stats`` (streaming/server
    measurements, once per wall second), ``busy``, ``pong``, ``error``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

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
    type: Literal["reset"]
    seed: int = Field(ge=0, le=2**32 - 1)


class Ping(BaseModel):
    type: Literal["ping"]
    id: int


ClientMessage = Annotated[SetSpeed | Reset | Ping, Field(discriminator="type")]
_client_adapter: TypeAdapter[SetSpeed | Reset | Ping] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str) -> SetSpeed | Reset | Ping:
    """Raises pydantic.ValidationError on malformed input."""
    return _client_adapter.validate_json(raw)


def speed_index(speed: float) -> int:
    return ALLOWED_SPEEDS.index(speed)


def hello(
    session_id: str, dt: float, tick_hz: float, params, duration_s: float, epoch: int,
    fmt: FrameFormat, segments: list[dict],
) -> dict:  # fmt: skip
    return {
        "type": "hello",
        "session_id": session_id,
        "dt": dt,
        "steps_per_second": STEPS_PER_SECOND,
        "tick_hz": tick_hz,
        "speeds": list(ALLOWED_SPEEDS),
        "seed": params.seed,
        "signal": params.signal,
        "demand_scale": params.demand_scale,
        "duration_s": duration_s,
        "epoch": epoch & 255,
        "classes": [
            {"name": c.name, "length_m": c.length_m, "width_m": c.width_m, "height_m": c.height_m}
            for c in VEHICLE_CLASSES
        ],
        "frame": fmt.to_dict(),
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
        "message": "Server busy: all simulation slots are in use. Please try again shortly.",
    }


def pong(ping_id: int) -> dict:
    return {"type": "pong", "id": ping_id}


def error(message: str, detail: Any = None) -> dict:
    return {"type": "error", "message": message, "detail": detail}
