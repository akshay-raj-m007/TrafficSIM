"""Cap on concurrent live simulations.

The server runs a single uvicorn worker and a single asyncio event loop, so this
in-memory counter is the global source of truth and needs no locking.
"""

from __future__ import annotations

import itertools
import time


class SessionManager:
    def __init__(self, max_sessions: int) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be >= 1")
        self.max_sessions = max_sessions
        self._active: dict[str, float] = {}  # session id -> start (monotonic)
        self._ids = itertools.count(1)
        self.rejected_total = 0
        self.closed: dict[str, int] = {}  # how sessions ended: disconnect, dead, idle, error

    def try_acquire(self) -> str | None:
        """Reserve a slot and return its session id, or None if the server is full."""
        if len(self._active) >= self.max_sessions:
            self.rejected_total += 1
            return None
        sid = f"s{next(self._ids)}"
        self._active[sid] = time.monotonic()
        return sid

    def release(self, sid: str, reason: str = "disconnect") -> None:
        if self._active.pop(sid, None) is not None:
            self.closed[reason] = self.closed.get(reason, 0) + 1

    def ages_s(self) -> list[float]:
        """Seconds each live session has been open, oldest first (health check)."""
        now = time.monotonic()
        return sorted((round(now - t0, 1) for t0 in self._active.values()), reverse=True)

    @property
    def active(self) -> int:
        return len(self._active)
