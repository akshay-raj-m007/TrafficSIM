"""Client-message handling of a live session (a mixin of ``LiveSession``).

Reset (seed / preset / scenario document, built off the event loop), apply (one live change),
export, speed and ping. The session supplies the sockets, the simulation and the build.
"""

from __future__ import annotations

import asyncio

from fastapi import WebSocketDisconnect
from pydantic import ValidationError

from trafficsim.server import live_scenario, protocol
from trafficsim.server.scenario_doc import ScenarioError, change_dict


class ClientHandlers:
    async def _reset(self, msg: protocol.Reset) -> None:
        try:
            if msg.scenario is not None:
                setup = live_scenario.from_doc(msg.scenario)
            elif msg.preset is not None:
                setup = live_scenario.from_preset(msg.preset, msg.seed)
            else:
                setup = self.setup.folded(self.sim, msg.seed)  # keeps the live edits
        except KeyError as exc:
            await self._send(
                protocol.rejected("reset", [{"path": "preset", "message": str(exc.args[0])}])
            )
            return
        except ScenarioError as exc:
            await self._send(protocol.rejected("reset", exc.items))
            return
        if self.building:
            text = "still building the previous scenario; try again when it is ready"
            await self._send(protocol.rejected("reset", [{"path": "(session)", "message": text}]))
            return
        self._build_task = asyncio.create_task(self._build(setup, "resetting"))

    async def _apply(self, raw: dict) -> None:
        if self.building:
            text = "still building the scenario; live changes are possible once it is ready"
            await self._send(protocol.rejected("apply", [{"path": "change", "message": text}]))
            return
        try:
            if len(self.sim.all_changes) >= self.settings.max_live_changes:
                raise ValueError(
                    f"this session already has {len(self.sim.all_changes)} live changes; the limit "
                    f"is {self.settings.max_live_changes}. Reset to start a new log."
                )
            change = live_scenario.live_change(raw, self.sim.tick)
            tick = self.sim.schedule(change)
        except ScenarioError as exc:
            await self._send(protocol.rejected("apply", exc.items))
            return
        except ValueError as exc:  # valid document, but cannot apply to the running simulation
            await self._send(protocol.rejected("apply", [{"path": "change", "message": str(exc)}]))
            return
        await self._send(protocol.applied(tick, change_dict(tick, change)))

    async def _reader(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                raw = await self.ws.receive_text()
                self._last_client_msg = loop.time()
                size = len(raw.encode("utf-8"))
                if size > self.settings.max_message_bytes:
                    limit = self.settings.max_message_bytes
                    text = f"message is {size} bytes; the limit is {limit}"
                    await self._send(
                        protocol.rejected("message", [{"path": "(message)", "message": text}])
                    )
                    continue
                try:
                    msg = protocol.parse_client_message(raw)
                except ValidationError as exc:
                    await self._send(
                        protocol.error(
                            "invalid message",
                            exc.errors(include_url=False, include_context=False)[:3],
                        )
                    )
                    continue
                if isinstance(msg, protocol.SetSpeed):
                    self.speed = msg.speed
                elif isinstance(msg, protocol.Reset):
                    await self._reset(msg)
                elif isinstance(msg, protocol.Apply):
                    await self._apply(msg.change)
                elif isinstance(msg, protocol.Export):
                    try:
                        await self._send(protocol.scenario_doc(
                            live_scenario.export_doc(self.setup, self.sim)))  # fmt: skip
                    except ScenarioError as exc:
                        await self._send(protocol.rejected("export", exc.items))
                elif isinstance(msg, protocol.Ping):
                    await self._send(protocol.pong(msg.id))
        except WebSocketDisconnect:
            return
