"""The only lanes and connectors allowed to carry nothing, and why.

Rule (tests/test_lane_utilisation.py): under the default demand every lane and connector that
is open to traffic carries vehicles, except those listed here. An entry needs a *reason* that
is true by construction of the demand or the scenario, not "it happens to be empty". The same
keys are listed in the README ("Lane utilisation"), and a test checks that they match.

Matching is on the segment id (``road:lane`` for a lane, ``from>to`` for a connector) and on
whether the flyover is open, so a structure with more or fewer lanes is covered by the same rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UtilisationException:
    key: str
    reason: str
    pattern: re.Pattern[str]
    flyover: bool | None = None  # applies only with the flyover open / closed; None = always


EXCEPTIONS: tuple[UtilisationException, ...] = (
    UtilisationException(
        "surface_through_at_j1",
        "J1 surface through movements (west to east, east to west): the flyover is the fastest "
        "route for every W<->E trip, so no origin-destination flow is routed through the "
        "signalised straight-ahead movement on the surface. They carry the W<->E traffic as "
        "soon as the flyover is closed (verified by the flyover_closed run of the report), so "
        "the exception applies only while it is open.",
        re.compile(r"^(eb_surf_w:\d+>eb_surf_e:\d+|wb_surf_e:\d+>wb_surf_w:\d+)$"),
        flyover=True,
    ),
    UtilisationException(
        "flyover_closed_structure",
        "Flyover closed: its ramps and deck are closed to traffic by definition.",
        re.compile(r"^(eb|wb)_(ramp_up|flyover|ramp_dn)[:_]"),
        flyover=False,
    ),
    UtilisationException(
        "flyover_closed_approach_lanes",
        "Flyover closed (default structure: lanes 2 and 3 of the 4-lane west road): the "
        "median-side lanes only lead onto the "
        "closed ramp (a vehicle there moves over to a surface lane), and the median-side "
        "lanes of its westbound exit are fed only by the closed ramp down.",
        re.compile(r"^(eb|wb)_w4:[2-9]$"),
        flyover=False,
    ),
)


def explain(segment_id: str, flyover_open: bool) -> UtilisationException | None:
    """The exception that allows ``segment_id`` to be empty, or None if none does."""
    for e in EXCEPTIONS:
        if e.flyover is not None and e.flyover != flyover_open:
            continue
        if e.pattern.match(segment_id):
            return e
    return None
