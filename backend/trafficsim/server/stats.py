"""Per-session streaming statistics, reported once per wall second (all measured)."""

from __future__ import annotations


class StreamStats:
    def __init__(self) -> None:
        self.frames_total = 0
        self.bytes_total = 0
        self.reset_window()

    def reset_window(self) -> None:
        self._steps_ms: list[float] = []
        self._encode_ms: list[float] = []
        self._bytes = 0
        self._frames = 0

    def add_frame(self, step_ms: float, encode_ms: float, nbytes: int) -> None:
        self._steps_ms.append(step_ms)
        self._encode_ms.append(encode_ms)
        self._bytes += nbytes
        self._frames += 1
        self.frames_total += 1
        self.bytes_total += nbytes

    def snapshot(self, window_s: float) -> dict:
        """Aggregates over the window since the last snapshot, then starts a new one."""
        n = max(self._frames, 1)
        out = {
            "frames": self._frames,
            "frame_bytes_mean": round(self._bytes / n),
            "bytes_per_s": round(self._bytes / window_s) if window_s > 0 else 0,
            "step_ms_mean": round(sum(self._steps_ms) / n, 3),
            "step_ms_max": round(max(self._steps_ms, default=0.0), 3),
            "encode_ms_mean": round(sum(self._encode_ms) / n, 3),
            "bytes_total": self.bytes_total,
            "frames_total": self.frames_total,
        }
        self.reset_window()
        return out
