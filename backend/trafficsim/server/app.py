"""FastAPI application: REST + WebSocket + the built frontend on a single origin.

Run with a single worker (session state and the session cap live in this process):
    uvicorn trafficsim.server.app:app --workers 1
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, Response, WebSocket
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from trafficsim import __version__
from trafficsim.engine.constants import DT
from trafficsim.network.demo import build_demo_network
from trafficsim.network.serialize import network_to_dict
from trafficsim.server import protocol
from trafficsim.server.config import Settings
from trafficsim.server.session_config import DEFAULT_SIGNAL, SessionParams
from trafficsim.server.sessions import SessionManager
from trafficsim.server.ws import LiveSession

BUSY_CLOSE_CODE = 1013  # RFC 6455 "Try Again Later"
BAD_REQUEST_CLOSE_CODE = 1008  # RFC 6455 "Policy Violation"


def _warm_up(network) -> None:
    """Measure what the signal controllers need (cached per process)."""
    from trafficsim.engine.calibration import saturation_flows
    from trafficsim.engine.scenario import DEFAULT_MIX

    for j in network.junctions:
        if j.control == "signalised":
            saturation_flows(network, DEFAULT_MIX, j.id)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    network = build_demo_network()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.warm_up:
            await asyncio.to_thread(_warm_up, network)
        yield

    app = FastAPI(title="TrafficSIM", version=__version__, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024)  # egress is metered on free hosts
    sessions = SessionManager(settings.max_sessions)
    network_json = json.dumps(network_to_dict(network), separators=(",", ":")).encode()
    app.state.settings = settings
    app.state.sessions = sessions

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "dt": DT,
            "sessions_active": sessions.active,
            "sessions_max": sessions.max_sessions,
            "sessions_rejected_total": sessions.rejected_total,
        }

    @app.get("/api/network")
    def get_network() -> Response:
        return Response(network_json, media_type="application/json")

    @app.websocket("/ws/sim")
    async def ws_sim(
        ws: WebSocket, seed: int = 42, signal: str = DEFAULT_SIGNAL, demand_scale: float = 1.0
    ) -> None:
        await ws.accept()
        try:  # experiment seam (query parameters); the UI has no controls for these yet
            params = SessionParams(seed=seed, signal=signal, demand_scale=demand_scale)
        except ValueError as exc:
            await ws.send_json(protocol.error(str(exc)))
            await ws.close(code=BAD_REQUEST_CLOSE_CODE)
            return
        sid = sessions.try_acquire()
        if sid is None:
            await ws.send_json(protocol.busy(sessions.max_sessions))
            await ws.close(code=BUSY_CLOSE_CODE)
            return
        try:
            await LiveSession(ws, sid, network, settings, params).run()
        finally:
            sessions.release(sid)
            with contextlib.suppress(RuntimeError):  # already closed by the client
                await ws.close()

    if settings.static_dir is not None and settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")

    return app


app = create_app()
