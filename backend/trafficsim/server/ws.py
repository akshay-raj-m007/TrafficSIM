"""One live simulation bound to one WebSocket connection.

Two concurrent tasks share the session:
  * ``_ticker`` — every 1/tick_hz s of wall time advances the sim by ``speed`` × the frame
    period (see ``pacing.StepPacer``; exact at any frame rate). If the simulation advanced
    it sends a binary vehicle frame (``frames.py``); a paused or finished simulation sends
    none. Once per wall second it also sends the measured KPIs and the streaming stats.
    Scheduling is drift-free (absolute deadlines from the loop clock); if the server
    falls more than one frame behind, it resynchronises instead of trying to catch up
    (frames are dropped, the sim never runs faster than requested).
  * ``_reader`` — applies client messages (speed, reset, apply a live change, export, ping).
Sends are serialised by a lock because both tasks write to the socket.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict

from fastapi import WebSocket

from trafficsim.engine.constants import DT
from trafficsim.network.types import Network
from trafficsim.server import live_scenario, protocol
from trafficsim.server.config import Settings
from trafficsim.server.frames import segment_table
from trafficsim.server.pacing import StepPacer
from trafficsim.server.scenario_doc import ScenarioError
from trafficsim.server.session_build import build_session
from trafficsim.server.session_config import SessionParams
from trafficsim.server.stats import StreamStats
from trafficsim.server.ws_client import ClientHandlers

AUX_PERIOD_S = 1.0  # KPI and stats messages, at most once per this many wall seconds


class LiveSession(ClientHandlers):
    def __init__(
        self, ws: WebSocket, sid: str, network: Network, settings: Settings,
        params: SessionParams | None = None,
    ) -> None:  # fmt: skip
        self.ws = ws
        self.sid = sid
        self.network = network
        self.settings = settings
        self.params = params or SessionParams()
        self.setup = live_scenario.from_params(self.params)
        self.epoch = 0
        self.speed: float = 1
        self.frames_dropped = 0
        self.stats = StreamStats()
        self._send_lock = asyncio.Lock()
        self._last_client_msg = 0.0
        self.sim = None  # built in run(), in a worker thread
        self.encoder = None
        self.building = False
        self._build_task: asyncio.Task | None = None

    async def _build(self, setup, reason: str, new_epoch: bool = True) -> None:
        """Build a simulation off the event loop (other sessions keep running), swap it in,
        send the hello. While it runs the ticker is idle and live changes are refused."""
        self.building = True
        try:
            await self._send(protocol.building(reason, setup.name))
            sim, encoder = await asyncio.to_thread(build_session, setup)
            self.setup, self.sim, self.encoder, self.network = setup, sim, encoder, setup.network
            if new_epoch:
                self.epoch = (self.epoch + 1) & 255
            await self._hello()
        except Exception as exc:  # the old simulation (if any) keeps running
            await self._send(protocol.error(f"could not build the scenario: {exc}"))
        finally:
            self.building = False

    def _export(self) -> dict | None:
        try:
            return live_scenario.export_doc(self.setup, self.sim)
        except ScenarioError:
            return None  # an experiment-only setup (uncontrolled signals) has no document

    async def _send(self, msg: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json(msg)

    async def _send_bytes(self, data: bytes) -> None:
        async with self._send_lock:
            await self.ws.send_bytes(data)

    async def _hello(self) -> None:
        await self._send(
            protocol.hello(
                self.sid,
                DT,
                self.settings.tick_hz,
                self.sim.scenario,
                self.params.demand_scale,
                self.epoch,
                self.encoder.fmt,
                segment_table(self.sim.lg),
                self._export(),
                asdict(self.setup.structure),
            )  # fmt: skip
        )
        await self._send_bytes(self.encoder.encode(self.epoch, protocol.speed_index(self.speed)))

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self._last_client_msg = loop.time()
        await self._build(self.setup, "starting the session", new_epoch=False)
        if self.sim is None:
            return
        tasks = [asyncio.create_task(self._ticker()), asyncio.create_task(self._reader())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (*tasks, self._build_task):
                if t is not None:
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ticker(self) -> None:
        loop = asyncio.get_running_loop()
        period = 1.0 / self.settings.tick_hz
        deadline = last_aux = loop.time()
        pacer = StepPacer(self.settings.tick_hz)
        while True:
            if self.building:  # a scenario is being built: nothing to step or send
                await asyncio.sleep(period)
                deadline = last_aux = loop.time()
                continue
            lag_ms = max(0.0, (loop.time() - deadline) * 1000.0)
            sim = self.sim
            t0 = time.perf_counter()
            taken = sim.step_n(pacer.steps_for_frame(self.speed))
            step_ms = (time.perf_counter() - t0) * 1000.0
            if taken:
                t1 = time.perf_counter()
                frame = self.encoder.encode(self.epoch, protocol.speed_index(self.speed))
                encode_ms = (time.perf_counter() - t1) * 1000.0
                await self._send_bytes(frame)
                self.stats.add_frame(step_ms, encode_ms, len(frame))
            now = loop.time()
            if now - last_aux >= AUX_PERIOD_S:
                agg = self.stats.snapshot(now - last_aux)
                agg["vehicles"] = sim.active
                last_aux = now
                await self._send(protocol.kpi(sim.kpi_snapshot()))
                await self._send(
                    protocol.stats(sim.time_s, sim.tick, self.speed, sim.done, lag_ms, agg)
                )
            if now - self._last_client_msg > self.settings.idle_timeout_s:
                await self._send(protocol.error("session closed after inactivity"))
                return
            deadline += period
            if now - deadline > period:  # more than a frame behind: resync, drop frames
                self.frames_dropped += int((now - deadline) / period)
                deadline = now
            await asyncio.sleep(max(0.0, deadline - now))
