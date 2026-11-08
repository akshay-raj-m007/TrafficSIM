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
from trafficsim.server.inspector import Inspector
from trafficsim.server.liveness import DEAD, IDLE, SEND_TIMEOUT_S, Liveness
from trafficsim.server.pacing import StepPacer
from trafficsim.server.scenario_doc import ScenarioError
from trafficsim.server.session_build import build_session, prepare_estimate
from trafficsim.server.session_config import SessionParams
from trafficsim.server.stats import StreamStats
from trafficsim.server.ws_client import ClientHandlers

STARVED_MS = 1000.0  # a frame this late means the event loop was blocked, not the peer gone
IDLE_CLOSE_CODE = 4000  # application close code: paused for inactivity
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
        self.live = Liveness(
            settings.heartbeat_timeout_s, settings.idle_timeout_s, time.monotonic()
        )
        self.close_reason = "disconnect"  # how the session ended (health: sessions_closed)
        self.sim = None  # built in run(), in a worker thread
        self.encoder = None
        self.building = False
        self.charts_on = False  # the results drawer is open: stream the chart measurements
        self.charts_seen: dict = {}  # cursors of what this session has received
        self.inspector = Inspector()  # the vehicle the browser is looking at, if any
        self.inspect_dirty = False
        self._build_task: asyncio.Task | None = None

    async def _build(self, setup, reason: str, new_epoch: bool = True) -> None:
        """Build a simulation off the event loop (other sessions keep running), swap it in,
        send the hello. While it runs the ticker is idle and live changes are refused."""
        self.building = True
        try:
            est = await asyncio.to_thread(prepare_estimate, setup)
            await self._send(protocol.building(reason, setup.name, est))
            loop = asyncio.get_running_loop()
            report = None if est is None else lambda d, n: asyncio.run_coroutine_threadsafe(
                self._send(protocol.building(reason, setup.name, est, d, n)), loop
            )  # fmt: skip
            sim, encoder = await asyncio.to_thread(build_session, setup, report)
            self.setup, self.sim, self.encoder, self.network = setup, sim, encoder, setup.network
            self.charts_seen = {}  # new simulation: history starts again
            self.inspector.select(None)  # vehicle ids belong to the old simulation
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
            await asyncio.wait_for(self.ws.send_json(msg), SEND_TIMEOUT_S)

    async def _send_bytes(self, data: bytes) -> None:
        async with self._send_lock:
            await asyncio.wait_for(self.ws.send_bytes(data), SEND_TIMEOUT_S)

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
        self.live = Liveness(
            self.settings.heartbeat_timeout_s, self.settings.idle_timeout_s, time.monotonic()
        )
        await self._build(self.setup, "starting the session", new_epoch=False)
        if self.sim is None:
            return
        tasks = [asyncio.create_task(self._ticker()), asyncio.create_task(self._reader())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            failed = any(t.exception() for t in done if not t.cancelled())
            if failed and self.close_reason == "disconnect":  # not already dead / idle
                self.close_reason = "error"  # a send timed out or the ticker / reader failed
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
            if self.inspector.active and (taken or self.inspect_dirty):
                self.inspect_dirty = False
                await self._send(self.inspector.message(sim))
            now = loop.time()
            if now - last_aux >= AUX_PERIOD_S:
                agg = self.stats.snapshot(now - last_aux)
                agg["vehicles"] = sim.active
                last_aux = now
                await self._send(protocol.kpi(sim.kpi_snapshot()))
                if self.charts_on:
                    await self._send(protocol.charts(sim.kpis.charts.since(self.charts_seen)))
                await self._send(
                    protocol.stats(sim.time_s, sim.tick, self.speed, sim.done, lag_ms, agg)
                )
            # A loop that was blocked for a while (a long build or measurement on a 0.1 CPU
            # instance) has not yet read the pings that are waiting: that is not a dead peer.
            verdict = None if lag_ms > STARVED_MS else self.live.verdict(time.monotonic())
            if verdict == DEAD:
                await asyncio.sleep(0.5)  # give the reader a turn, then look again
                verdict = self.live.verdict(time.monotonic())
            if verdict == DEAD:  # nothing heard for heartbeat_timeout_s: free the slot
                self.close_reason = DEAD
                return
            if verdict == IDLE:  # open but nobody there: pause (close) and tell the page
                self.close_reason = IDLE
                await self._send(protocol.idle(self.settings.idle_timeout_s / 60.0))
                await self.ws.close(code=IDLE_CLOSE_CODE)
                return
            deadline += period
            if now - deadline > period:  # more than a frame behind: resync, drop frames
                self.frames_dropped += int((now - deadline) / period)
                deadline = now
            await asyncio.sleep(max(0.0, deadline - now))
