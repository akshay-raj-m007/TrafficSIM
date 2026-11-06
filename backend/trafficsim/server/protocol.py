"""WebSocket message schemas.

Client -> server messages are validated with pydantic. Server -> client messages are
small dicts built by the helpers below (JSON for now; vehicle frames will be binary).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

ALLOWED_SPEEDS: tuple[int, ...] = (0, 1, 2, 5, 10)
Speed = Literal[0, 1, 2, 5, 10]


class SetSpeed(BaseModel):
    type: Literal["set_speed"]
    speed: Speed


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


def hello(session_id: str, dt: float, tick_hz: float, seed: int, duration_s: float) -> dict:
    return {
        "type": "hello",
        "session_id": session_id,
        "dt": dt,
        "tick_hz": tick_hz,
        "speeds": list(ALLOWED_SPEEDS),
        "seed": seed,
        "duration_s": duration_s,
    }


def tick(tick_n: int, t: float, speed: int, done: bool, step_ms: float, lag_ms: float) -> dict:
    return {
        "type": "tick",
        "tick": tick_n,
        "t": t,
        "speed": speed,
        "done": done,
        "step_ms": round(step_ms, 3),  # measured server compute time for this frame
        "lag_ms": round(lag_ms, 1),  # how late this frame left vs its schedule
    }


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
