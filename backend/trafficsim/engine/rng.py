"""Seeded, named random-number streams.

Every stochastic subsystem draws from its *own* stream, spawned deterministically from
the scenario seed via ``numpy.random.SeedSequence``. Consequences:

* same seed  ⇒ identical draws in every stream (determinism invariant);
* adding or removing draws in one subsystem (e.g. route choice) cannot shift the
  numbers seen by another (e.g. spawning);
* child ``i`` of a ``SeedSequence`` depends only on ``(seed, i)``, so appending a new
  stream name at the END of ``STREAM_NAMES`` leaves existing streams unchanged.
  Never reorder or insert names in the middle.
"""

from __future__ import annotations

from typing import Final

import numpy as np

STREAM_NAMES: Final[tuple[str, ...]] = (
    "spawn",  # arrival process (headways)
    "vehicle_class",  # class mix draws
    "route",  # origin-destination / route choice
    "behaviour",  # per-driver parameter heterogeneity
)


class RngStreams:
    """A fixed set of independent PCG64 generators derived from one integer seed."""

    __slots__ = ("seed", "_gens")

    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ValueError(f"seed must be a non-negative int, got {seed!r}")
        self.seed: int = seed
        children = np.random.SeedSequence(seed).spawn(len(STREAM_NAMES))
        self._gens: dict[str, np.random.Generator] = {
            name: np.random.Generator(np.random.PCG64(child))
            for name, child in zip(STREAM_NAMES, children, strict=True)
        }

    def get(self, name: str) -> np.random.Generator:
        try:
            return self._gens[name]
        except KeyError:
            raise KeyError(f"unknown RNG stream {name!r}; known: {STREAM_NAMES}") from None

    @property
    def spawn(self) -> np.random.Generator:
        return self._gens["spawn"]

    @property
    def vehicle_class(self) -> np.random.Generator:
        return self._gens["vehicle_class"]

    @property
    def route(self) -> np.random.Generator:
        return self._gens["route"]

    @property
    def behaviour(self) -> np.random.Generator:
        return self._gens["behaviour"]

    def state_fingerprint(self) -> tuple[tuple[str, int, int], ...]:
        """Compact, comparable snapshot of every stream's internal state."""
        out = []
        for name in STREAM_NAMES:
            st = self._gens[name].bit_generator.state["state"]
            out.append((name, int(st["state"]), int(st["inc"])))
        return tuple(out)
