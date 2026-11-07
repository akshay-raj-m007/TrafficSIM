"""REST endpoints of the A/B comparison (see compare_jobs.py for the machinery).

GET    /api/compare/limits   what this server allows (runs, duration, defaults)
POST   /api/compare          start a comparison -> job (422 errors, 429 busy)
GET    /api/compare/{id}     progress, then the result
DELETE /api/compare/{id}     cancel
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from trafficsim.server import experiments
from trafficsim.server.compare_jobs import CompareBusy, CompareManager, RunCache
from trafficsim.server.compare_spec import (
    ALLOWED_RUNS,
    DEFAULT_DURATION_S,
    DEFAULT_WARMUP_S,
    CompareError,
)
from trafficsim.server.config import Settings


async def bounded_json(request: Request, limit: int):
    """The JSON body, or a 413 / 422 response naming the limit or the problem."""
    declared = int(request.headers.get("content-length") or 0)
    body = await request.body() if declared <= limit else b""
    if declared > limit or len(body) > limit:
        n = declared or len(body)
        return JSONResponse(
            {
                "errors": [
                    {"path": "(request)", "message": f"body is {n} bytes; the limit is {limit}"}
                ]
            },
            status_code=413,
        )
    try:
        return json.loads(body)
    except ValueError as exc:
        return JSONResponse(
            {"errors": [{"path": "(request)", "message": f"not JSON: {exc}"}]}, status_code=422
        )


def register(app: FastAPI, settings: Settings) -> CompareManager:
    manager = CompareManager(settings.compare, RunCache(settings.cache_dir))
    lim = settings.compare
    for exp_id in experiments.definitions():  # shipped runs also serve custom comparisons
        if (doc := experiments.stored(exp_id)) is not None:
            manager.cache.memory.update(doc["runs"])

    @app.get("/api/experiments")
    def list_experiments() -> list[dict]:
        return experiments.listing()

    @app.get("/api/experiments/{exp_id}")
    def get_experiment(exp_id: str) -> JSONResponse:
        doc = experiments.stored(exp_id)
        if doc is None:
            return JSONResponse({"detail": "unknown or not generated experiment"}, status_code=404)
        return JSONResponse(doc | {"stale": experiments.is_stale(doc)})

    @app.get("/api/compare/limits")
    def limits() -> dict:
        return {
            "runs": [r for r in ALLOWED_RUNS if r <= lim.max_runs],
            "max_duration_s": lim.max_duration_s, "max_jobs": lim.max_jobs,
            "default_duration_s": min(DEFAULT_DURATION_S, lim.max_duration_s),
            "default_warmup_s": DEFAULT_WARMUP_S,
        }  # fmt: skip

    @app.post("/api/compare")
    async def start(request: Request) -> JSONResponse:
        raw = await bounded_json(request, settings.max_request_bytes)
        if isinstance(raw, JSONResponse):
            return raw
        try:
            return JSONResponse(manager.submit(raw).to_dict())
        except CompareError as exc:
            return JSONResponse({"errors": exc.items}, status_code=422)
        except CompareBusy as exc:
            return JSONResponse(
                {"errors": [{"path": "(server)", "message": str(exc)}]}, status_code=429
            )

    @app.get("/api/compare/{job_id}")
    def status(job_id: str) -> JSONResponse:
        job = manager.get(job_id)
        if job is None:
            return JSONResponse({"detail": "unknown comparison"}, status_code=404)
        return JSONResponse(job.to_dict())

    @app.delete("/api/compare/{job_id}")
    def cancel(job_id: str) -> dict:
        return {"cancelled": manager.cancel(job_id)}

    return manager
