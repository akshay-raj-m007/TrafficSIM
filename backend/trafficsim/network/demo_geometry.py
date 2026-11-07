"""Derived geometry of the demo network for a given ``Structure``.

Everything that depends on the lane counts and widths is computed here, in one place. The
numbers marked "from the default" are the original hand-chosen layout expressed as a rule
(rise or clearance beyond a lane), so the default structure reproduces the original network
exactly and other structures keep the same turn-path proportions: a turn path must stay
longer than the longest vehicle (12 m), which the rules guarantee for every allowed structure
(tests/test_network_structures.py builds all of them).
"""

from __future__ import annotations

from dataclasses import dataclass

from trafficsim.network.structure import Structure

MEDIAN_HALF = 1.0  # half-width of the central median
W_LINK = 3.0  # the single narrow J1 link lane (fixed)
# J1 box half-height = the larger of (kerb-lane centre + rise) and (link-lane centre + clearance);
# both equal 20 m for the default structure (13.25 + 6.75 and 9.75 + 10.25).
J1_KERB_RISE_M = 6.75
J1_LINK_CLEARANCE_M = 10.25
# J2 minor road: its exit lane starts this far beyond the major road's kerb-lane centre, and
# the two-lane approach stops further out (default 6.25 + 5.75 = 12 m and 6.25 + 8.75 = 15 m).
J2_EXIT_RISE_M = 5.75
J2_STOP_RISE_2LANE_M = 8.75


@dataclass(frozen=True)
class Derived:
    surf_inner: float  # distance of the surface lanes' median edge from the reference line
    link_inner: float  # same for the single link lane
    kerb_centre_y: float  # centre of the surface kerb lane
    link_y: float  # centre of the link lane
    j1_half_y: float  # J1 box half-height (cross-street arms start here)
    major_half: float  # J2 major road half-width (median + flyover group)
    j2_kerb_y: float  # centre of the major road's kerb lane at J2
    j2_exit_y: float  # where J2's minor exit lane starts
    j2_stop_y: float  # where J2's minor approach stops

    @classmethod
    def of(cls, st: Structure) -> Derived:
        s, f, ws, wf = st.surface_lanes, st.flyover_lanes, st.surface_width_m, st.flyover_width_m
        surf_inner = MEDIAN_HALF + f * wf
        link_inner = surf_inner + wf / 2 - W_LINK / 2
        kerb_centre_y = surf_inner + (s - 1) * ws + ws / 2
        link_y = surf_inner + wf / 2
        major_half = MEDIAN_HALF + f * wf
        j2_kerb_y = MEDIAN_HALF + (f - 1) * wf + wf / 2
        stop_rise = J2_STOP_RISE_2LANE_M if st.j2_minor_lanes > 1 else J2_EXIT_RISE_M
        return cls(
            surf_inner=surf_inner, link_inner=link_inner, kerb_centre_y=kerb_centre_y,
            link_y=link_y,
            j1_half_y=max(kerb_centre_y + J1_KERB_RISE_M, link_y + J1_LINK_CLEARANCE_M),
            major_half=major_half, j2_kerb_y=j2_kerb_y, j2_exit_y=j2_kerb_y + J2_EXIT_RISE_M,
            j2_stop_y=j2_kerb_y + stop_rise,
        )  # fmt: skip
