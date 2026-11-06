"""Helpers for WebSocket tests: messages are either binary frames or JSON text."""

from __future__ import annotations

import json
import time

from starlette.websockets import WebSocketDisconnect

from trafficsim.server.frames import FrameFormat, unpack_frame


def recv(ws):
    """Next message: bytes for a binary frame, dict for JSON."""
    m = ws.receive()
    if m["type"] == "websocket.close":
        raise WebSocketDisconnect(m.get("code", 1000))
    return m["bytes"] if m.get("bytes") is not None else json.loads(m["text"])


def next_json(ws, kind: str, limit: int = 4000) -> dict:
    for _ in range(limit):
        m = recv(ws)
        if isinstance(m, dict) and m["type"] == kind:
            return m
    raise AssertionError(f"no {kind!r} message within {limit} messages")


def next_frame(ws, limit: int = 4000) -> bytes:
    for _ in range(limit):
        m = recv(ws)
        if isinstance(m, bytes):
            return m
    raise AssertionError("no binary frame")


def hello_and_format(ws) -> tuple[dict, FrameFormat]:
    hello = next_json(ws, "hello")
    return hello, FrameFormat(**hello["frame"])


def decoded(ws, fmt: FrameFormat) -> dict:
    return unpack_frame(fmt, next_frame(ws))


def timed_frames(ws, fmt: FrameFormat, seconds: float, speed_index: int):
    """(wall seconds, sim ticks) between the first and last frame of one speed in a window."""
    first = None
    while True:
        m = recv(ws)
        if not isinstance(m, bytes):
            continue
        f = unpack_frame(fmt, m)
        now = time.perf_counter()
        if f["speed_index"] != speed_index:
            continue
        if first is None:
            first = (now, f["tick"])
        elif now - first[0] >= seconds:
            return now - first[0], f["tick"] - first[1]
