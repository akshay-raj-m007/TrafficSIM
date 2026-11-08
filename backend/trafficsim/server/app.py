"""FastAPI application: REST + WebSocket + the built frontend on a single origin.

Run with a single worker (session state and the session cap live in this process):
    uvicorn trafficsim.server.app:app --workers 1
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from trafficsim import __version__
from trafficsim.engine import tablecache
from trafficsim.engine.constants import DT
from trafficsim.network.demo import build_demo_network
from trafficsim.network.serialize import network_to_dict
from trafficsim.network.structure import Structure
from trafficsim.server import compare_api, protocol, validation_doc
from trafficsim.server.config import Settings
from trafficsim.server.presets_doc import PRESET_INFO, all_presets
from trafficsim.server.scenario_doc import problems
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


@functools.lru_cache(maxsize=32)
def network_bytes(structure: Structure) -> bytes:
    """The network JSON of one structure (built once, then cached)."""
    net = build_demo_network(structure)
    return json.dumps(network_to_dict(net), separators=(",", ":")).encode()


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
    app.state.settings = settings
    app.state.sessions = sessions
    if settings.cache_dir is not None:  # measured tables are shared with worker processes
        os.environ.setdefault(tablecache.ENV_VAR, str(settings.cache_dir.parent / "tables"))
    app.state.compare = compare_api.register(app, settings)

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "dt": DT,
            "sessions_active": sessions.active,
            "sessions_max": sessions.max_sessions,
            "sessions_rejected_total": sessions.rejected_total,
            "session_ages_s": sessions.ages_s(),
            "sessions_closed": sessions.closed,
            "heartbeat_timeout_s": settings.heartbeat_timeout_s,
            "idle_timeout_s": settings.idle_timeout_s,
        }

    @app.get("/api/network")
    def get_network(
        j2_minor_lanes: int = 2, surface_lanes: int = 2, flyover_lanes: int = 2,
        surface_width_m: float = 3.5, flyover_width_m: float = 3.5,
    ) -> Response:  # fmt: skip
        try:
            st = Structure(j2_minor_lanes, surface_lanes, flyover_lanes, surface_width_m,
                           flyover_width_m)  # fmt: skip
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)
        return Response(network_bytes(st), media_type="application/json")

    @app.get("/api/validation")
    def get_validation() -> JSONResponse:
        doc = validation_doc.stored()
        if doc is None:
            return JSONResponse({"detail": "no stored validation results"}, status_code=404)
        return JSONResponse(doc | {"stale": validation_doc.is_stale(doc)})

    @app.get("/api/presets")
    def get_presets() -> dict:
        return {n: {"info": PRESET_INFO[n], "scenario": d} for n, d in all_presets().items()}

    @app.post("/api/scenario/validate")
    async def validate_scenario(request: Request) -> JSONResponse:
        raw = await compare_api.bounded_json(request, settings.max_request_bytes)
        if isinstance(raw, JSONResponse):
            return raw
        found = problems(raw)
        return JSONResponse({"valid": not found, "errors": found})

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
        live = LiveSession(ws, sid, network, settings, params)
        try:
            await live.run()
        except BaseException:
            live.close_reason = live.close_reason or "error"
            raise
        finally:
            sessions.release(sid, live.close_reason)  # always, whatever ended the session
            # the client may already be gone (abrupt disconnect): nothing left to close
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await ws.close()

    if settings.static_dir is not None and settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")

    return app


app = create_app()
