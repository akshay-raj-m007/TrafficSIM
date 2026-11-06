"""One live simulation bound to one WebSocket connection.

Two concurrent tasks share the session:
  * ``_ticker`` — every 1/tick_hz s of wall time advances the sim by ``speed`` × the frame
    period (see ``pacing.StepPacer``; exact at any frame rate) and sends a frame.
    Scheduling is drift-free (absolute deadlines from the loop clock); if the server
    falls more than one frame behind, it resynchronises instead of trying to catch up
    (frames are dropped, the sim never runs faster than requested).
  * ``_reader`` — applies client messages (speed, reset, ping).
Sends are serialised by a lock because both tasks write to the socket.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from trafficsim.engine.constants import DT
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario
from trafficsim.network.types import Network
from trafficsim.server import protocol
from trafficsim.server.config import Settings
from trafficsim.server.pacing import StepPacer

DEFAULT_SEED = 42


class LiveSession:
    def __init__(self, ws: WebSocket, sid: str, network: Network, settings: Settings) -> None:
        self.ws = ws
        self.sid = sid
        self.network = network
        self.settings = settings
        self.sim = Simulation(network, Scenario(seed=DEFAULT_SEED))
        self.speed = 1
        self.frames_dropped = 0
        self._send_lock = asyncio.Lock()
        self._last_client_msg = 0.0

    async def _send(self, msg: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json(msg)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self._last_client_msg = loop.time()
        sc = self.sim.scenario
        await self._send(
            protocol.hello(self.sid, DT, self.settings.tick_hz, sc.seed, sc.duration_s)
        )
        tasks = [asyncio.create_task(self._ticker()), asyncio.create_task(self._reader())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ticker(self) -> None:
        loop = asyncio.get_running_loop()
        period = 1.0 / self.settings.tick_hz
        deadline = loop.time()
        pacer = StepPacer(self.settings.tick_hz)
        while True:
            lag_ms = max(0.0, (loop.time() - deadline) * 1000.0)
            t0 = time.perf_counter()
            self.sim.step_n(pacer.steps_for_frame(self.speed))
            step_ms = (time.perf_counter() - t0) * 1000.0
            sim = self.sim
            await self._send(
                protocol.tick(sim.tick, sim.time_s, self.speed, sim.done, step_ms, lag_ms)
            )
            if loop.time() - self._last_client_msg > self.settings.idle_timeout_s:
                await self._send(protocol.error("session closed after inactivity"))
                return
            deadline += period
            now = loop.time()
            if now - deadline > period:  # more than a frame behind: resync, drop frames
                self.frames_dropped += int((now - deadline) / period)
                deadline = now
            await asyncio.sleep(max(0.0, deadline - now))

    async def _reader(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                raw = await self.ws.receive_text()
                self._last_client_msg = loop.time()
                try:
                    msg = protocol.parse_client_message(raw)
                except ValidationError as exc:
                    await self._send(protocol.error("invalid message", exc.errors()[:3]))
                    continue
                if isinstance(msg, protocol.SetSpeed):
                    self.speed = msg.speed
                elif isinstance(msg, protocol.Reset):
                    self.sim = Simulation(self.network, Scenario(seed=msg.seed))
                elif isinstance(msg, protocol.Ping):
                    await self._send(protocol.pong(msg.id))
        except WebSocketDisconnect:
            return
