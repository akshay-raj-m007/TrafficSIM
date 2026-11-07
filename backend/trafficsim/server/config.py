"""Server settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from trafficsim.server.compare_spec import CompareLimits

_REPO_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
_DEFAULT_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "compare"


@dataclass(frozen=True, slots=True)
class Settings:
    # Concurrent live simulations. Each one is CPU-bound; Render free = 0.1 CPU.
    max_sessions: int = 2
    # Directory with the built React app; None disables static serving (API only).
    static_dir: Path | None = None
    # WebSocket frame rate (wall clock). Each frame advances `speed` sim steps.
    tick_hz: float = 10.0
    # Close a live session after this long without any client message (incl. pings).
    idle_timeout_s: float = 900.0
    # Measure the J1 saturation flows at start-up (about 7 s) instead of in the first
    # session that needs them.
    warm_up: bool = True
    # A/B comparisons (server/compare_jobs.py): limits a hosted server can tighten, and
    # where finished runs are cached (None: memory only).
    compare: CompareLimits = CompareLimits()
    cache_dir: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        static = os.environ.get("STATIC_DIR")
        static_dir = Path(static) if static else (_REPO_DIST if _REPO_DIST.is_dir() else None)
        return cls(
            max_sessions=int(os.environ.get("MAX_SESSIONS", "2")),
            static_dir=static_dir,
            tick_hz=float(os.environ.get("TICK_HZ", "10")),
            idle_timeout_s=float(os.environ.get("SESSION_IDLE_TIMEOUT_S", "900")),
            warm_up=os.environ.get("WARM_UP", "1") != "0",
            compare=CompareLimits(
                max_runs=int(os.environ.get("COMPARE_MAX_RUNS", "10")),
                max_duration_s=float(os.environ.get("COMPARE_MAX_DURATION_S", "1800")),
                max_jobs=int(os.environ.get("COMPARE_MAX_JOBS", "1")),
                workers=int(os.environ.get("COMPARE_WORKERS", "0")),
            ),
            cache_dir=Path(os.environ.get("COMPARE_CACHE_DIR", _DEFAULT_CACHE)),
        )
