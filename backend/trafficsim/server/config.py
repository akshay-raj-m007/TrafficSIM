"""Server settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


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
        )
