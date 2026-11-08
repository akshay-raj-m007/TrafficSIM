"""Is the other end of a live session still there, and is anyone using it?

Two clocks per session, both fed by the messages the browser sends:

heartbeat  any message at all, pings included (the browser pings every 2 s). If none arrives
           for ``heartbeat_s`` the connection is treated as dead: a browser that vanished
           without closing the socket (a closed laptop, a lost network, a proxy that keeps its
           side of the connection open and so hides the loss) would otherwise hold its slot for
           ever, because the server only learns about a disconnect from the socket.
activity   a message that is not a ping: a control, or the browser's throttled "activity"
           notice (mouse, keys, touch). A session open for ``idle_s`` without any is *idle*:
           it is paused and closed, the page asks the visitor to click to resume.
"""

from __future__ import annotations

SEND_TIMEOUT_S = 10.0  # a send that takes longer means the peer is not reading: the session ends
DEAD = "dead"
IDLE = "idle"


class Liveness:
    def __init__(self, heartbeat_s: float, idle_s: float, now: float) -> None:
        self.heartbeat_s = heartbeat_s
        self.idle_s = idle_s
        self._beat = self._active = now

    def heartbeat(self, now: float) -> None:
        self._beat = now

    def activity(self, now: float) -> None:
        self._beat = self._active = now

    def verdict(self, now: float) -> str | None:
        """DEAD (no message for heartbeat_s), IDLE (only pings for idle_s) or None."""
        if now - self._beat > self.heartbeat_s:
            return DEAD
        if now - self._active > self.idle_s:
            return IDLE
        return None
