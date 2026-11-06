"""Cap on concurrent live simulations.

The server runs a single uvicorn worker and a single asyncio event loop, so this
in-memory counter is the global source of truth and needs no locking.
"""

from __future__ import annotations

import itertools


class SessionManager:
    def __init__(self, max_sessions: int) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be >= 1")
        self.max_sessions = max_sessions
        self._active: dict[str, None] = {}
        self._ids = itertools.count(1)
        self.rejected_total = 0

    def try_acquire(self) -> str | None:
        """Reserve a slot and return its session id, or None if the server is full."""
        if len(self._active) >= self.max_sessions:
            self.rejected_total += 1
            return None
        sid = f"s{next(self._ids)}"
        self._active[sid] = None
        return sid

    def release(self, sid: str) -> None:
        self._active.pop(sid, None)

    @property
    def active(self) -> int:
        return len(self._active)
