# TrafficSIM — project state 8: link follows the surface group, widths and capacities

Continues `project_state_7.md`. Written Sat 7 Nov 2026, late evening, before deployment. **Deadline: Mon 9 Nov 2026, 18:08
IST.** Features are frozen after this round (user decision).

## What changed
1. **The link east of J1 follows the surface group** (lane count, width, position): `network/demo_corridor.py`,
   `demo_geometry.py`, `demo.py` (J1 east arm now has S lanes with the same turn rule as the west arm, through lanes keep their
   index, cross-street left turns enter the kerb link lane, right turns the median-side one). East of the merge the road has
   S link lanes + F flyover lanes; the S link lanes end at the lane drop. **Consequence for the default network (2+2 lanes):
   it is no longer the original network (the link was one 3.0 m lane), the lane drop is 4 -> 2, and there is no 3-lane road
   by default (3-lane roads appear with 3 surface or flyover lanes).** A fingerprint test shows that only the four link roads
   and the connectors touching them changed.
2. **Lane planning one road ahead at junction approaches** (`engine/routes.py`): found because the left-only lane of J1's east
   arm held a stopped through vehicle that could not leave it. A lane is good on a road before a junction approach only if it
   enters a good lane there.
3. **Demand constants re-derived** with the existing tools: J1 Y 0.676, rush x1.26 (4,906 veh/h), J2 minor 230 / 14 veh/h.
4. **Experiments (5 built in):** policy, flyover open/closed, surface lanes with the flyover closed, flyover width alone,
   flyover 2 vs 1 lane. Widths and capacities results are in the README ("Widths and capacities"): lane count matters when
   the lanes are the bottleneck (flyover closed, 3 vs 2 surface lanes: -991 veh/h for the narrower road; flyover 2 vs 1
   lane: -1,303 veh/h); **width alone has no significant effect on delay, throughput or queues** (flyover 2 x 3.5 m vs
   2 x 2.75 m: delay +0.6 s [-1.2, +2.3]) because width acts only on desired speed in this model, which shows in travel time
   (+17.4 s median), not in delay (measured against each structure's own free-flow time).
5. **Merge rule** (`engine/merge_turns.py`, per green): kept as a safeguard, dormant at J1 now; the evidence (no rule 10.8,
   per vehicle 4.0, per green 11.0 through entries per 120 s; admission only when the previous rear has cleared the 30 m box
   connector's end, so the next vehicle starts from rest) is in the README as a known limitation. **User decision: keep.**
6. **Utilisation exceptions by structure**: `surface_through_lanes` (middle surface lanes with 3-4 surface lanes while the
   flyover is open); `explain(id, flyover_open, surface_lanes)`.
7. Small: the seed field can be emptied with backspace (empty used to refill with the running seed); tests renamed/updated
   for the new ids (`eb_surf_w:1>eb_surf_e:1`, `wb_surf_e:1>wb_surf_w:1`).

## Answers given to the user
- "0 against 68" in the unserved row of the flyover-closed experiment: the 68 (first version) was arm B, 2 lanes x 2.75 m; arm
  A had 0. With the new link: A 0.5, B 189.6.

## Open / not done
- The J2 right turn carries nothing at rush hour (gap acceptance; not a lane-choice bug); only the default is tested for
  utilisation.
- No true zipper merge (time-gap admission), not attempted (collision-critical).
- Meter overhead 5.4% of step time, unchanged. F10-F13 of `project_state_5.md` unchanged. Deployment parked until tomorrow.
