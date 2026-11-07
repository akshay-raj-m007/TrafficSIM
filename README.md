# TrafficSIM

Agent-based traffic simulator on a hand-built road network: two junctions (signalised and
give-way), a flyover with diverge/merge ramps, roads with 1–4 lanes, and a 3→2 lane drop.
It is meant to be used as a small research workbench.

- **Engine:** Python 3.12 + NumPy. IDM car-following and MOBIL lane changes (step 2), fixed
  `dt = 0.1 s`, seeded and deterministic. Tested with pytest.
- **Server:** FastAPI. Each browser session gets its own simulation, streamed over a WebSocket
  at 10 Hz. Concurrent sessions are capped, and extra visitors see a "server busy" message.
- **Frontend:** Vite + React + Three.js. A true metric 3D view (1 unit = 1 m) with scenario
  controls and measured telemetry.

> Status: **step 2b done**: vehicles are drawn in the 3D view with smooth motion, and the
> right panel shows KPIs measured in the backend. Scenario controls come in step 3.
> Deployment is parked: this runs on localhost.

## Run locally

```bash
# backend (Python 3.12)
cd backend
py -3.12 -m venv .venv            # or: python3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -m "not slow"   # fast subset (~45 s)
.venv/Scripts/python -m pytest                  # everything (~5 min; this is what CI runs)
.venv/Scripts/python -m uvicorn trafficsim.server.app:app --port 8000

# frontend (Node 22+), in a second terminal
cd frontend
npm ci
npm run dev                        # http://localhost:5173 (proxies /api and /ws to :8000)
npm run lint && npm test && npm run build
```

Single-origin production image:

```bash
docker build -t trafficsim .
docker run --rm -p 8000:8000 trafficsim   # http://localhost:8000
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | status, `dt`, active / max / rejected sessions |
| `GET /api/network?j2_minor_lanes=1\|2` | the network geometry (metres; x east, y north, z up) |
| `GET /api/presets` | the four named scenarios (documents) with a one-line description each |
| `POST /api/compare`, `GET /api/compare/{id}`, `DELETE /api/compare/{id}`, `GET /api/compare/limits` | start an A/B comparison (422 with per-field errors, 429 when the job cap is reached), poll its progress and result, cancel, read the server limits |
| `GET /api/experiments[/{id}]` | the precomputed built-in experiments |
| `POST /api/scenario/validate` | validate a scenario document: `{valid, errors: [{path, message}]}` |
| `WS /ws/sim` | live session. Server to client: `hello` (class sizes, frame format, segment table, the scenario document in force, network key), binary vehicle frames (only when the simulation advanced), `kpi` and `stats` (once per second), `applied` / `rejected` (answers to `apply` and `reset`), `scenario` (answer to `export`), `busy`. Client to server: `set_speed` (0, 0.25, 0.5, 1, 2, 5, 10), `reset` (`seed`, or `preset` [+ `seed`], or a whole `scenario` document), `apply` (one live change), `export`, `ping`. Close code 1013 when full. Optional query parameters `seed`, `signal` (`fixed_webster`, `max_pressure`, `max_pressure_threshold`, `uncontrolled`) and `demand_scale` (0.25 to 3) are an experiment seam |

### Scenario editor, JSON and live changes

The left panel is the scenario editor. **Live settings** change while the simulation runs;
**structural settings** (the J2 minor approach: one shared lane or two turn lanes) are marked
*applies on reset* and show *pending until reset* while they differ from the running network.

| Live setting | Behaviour |
|---|---|
| Demand (veh/h, per origin-destination pair; per-origin total keeps the split; scale all) | a zone whose total rate changes redraws its next arrival as now + Exp(new rate) from the arrival stream (valid because the exponential is memoryless) |
| Vehicle mix (percent, must add up to exactly 100) | applies to vehicles generated afterwards. **It does not retime the signals** (see "Signal plans keep their design" below) |
| J1 signal policy (Webster, max-pressure, thresholded max-pressure) | the new controller continues in the current phase and state, finishes the running amber and all-red, then decides for itself, so two conflicting greens cannot occur. The controllers are built from the scenario's **design record** (below), so a switch never measures or recomputes anything |
| Flyover open / closed | see below |

**Closing the flyover.** The deck and both ramps stop accepting vehicles. Entry queues and
arrivals are routed over the surface, and so is every vehicle that can still change its
route, including one inside a junction (it chooses from the road it is entering). A vehicle
on the deck or a ramp finishes its trip. A vehicle upstream of the diverge that would need
lane changes it cannot make in the distance left (lanes to cross x 3 s lane-change cooldown
x speed limit) keeps its flyover route (it is "grandfathered"): stranding it at the end of
a lane that no longer leads anywhere would block the lane. Reopening applies the same rule in
reverse. **Delay is measured against the fastest free-flow route on the fully open network**
for the vehicle's origin, destination and class, for everyone (re-routed or inserted after the
closure alike), so the extra time a closure causes counts as delay (a lone car forced onto the
surface takes 27 s longer than on the flyover and shows 27 s of delay; tested).

**Every live change is logged with the tick it was applied at**, changes apply at a tick
boundary before the first phase of that tick, and `Simulation.change_log` plus the seed
reproduces the run exactly (`tests/engine/test_live_changes.py`: per-step state hashes
identical across replays and between live scheduling and replaying the logged scenario).

**Scenario JSON** (one schema, version 1, `server/scenario_doc.py`): `version`, `name`,
`seed`, `duration_s`, `structure.j2_minor_lanes`, `initial` (per-pair demand, mix in percent,
policy, `flyover_open`) and `changes` (the log). Nothing is clamped, defaulted or
renormalised; every problem comes back as `{path, message}` (for example
`initial.mix: shares sum to 97, must be exactly 100`), and unknown fields are rejected.
Export and import are buttons in the panel; importing an export gives the same document back.

**Presets:** `default`; `rush_hour` (every flow x1.11, which takes J1's critical flow ratio Y
from 0.763 to 0.847, both from the measured saturation flows; the unbounded Webster cycle would then
be 378 s, the applied one stays at the 120 s cap; before the cross-street <-> arterial flows were
added: x1.31, Y 0.649 -> 0.850); `flyover_closed`; `j2_before` (one shared minor lane, otherwise the
default).

**Default J2 minor demand, from measured capacities** (`tools/measure_j2_capacity.py`, both
movements saturated under the default major-road demand, seeds 1-3, 900 s, first 300 s
excluded): left turn served 366, 312, 198 veh/h (mean 292), right turn 6, 96, 12 veh/h
(mean 38). Each default flow is 0.8 x the measured mean: **234 veh/h left, 30 veh/h right**
(before the cross-street flows: 214 / 37). Both vary a lot between seeds, so on the weakest seed
234 left is above its capacity.

### Structure: lane counts and widths (applies on reset)

Two lane groups meet at the diverge and are editable per direction (1-4 lanes, 2.5-4.0 m,
defaults 2 lanes at 3.5 m; the panel shows "pending until reset" while the draft differs from the
running network, and an out-of-range value is an error next to its field, never clamped):

- the **surface group** (the road through J1): `surface_lanes`, `surface_width_m`;
- the **flyover / through group** (ramps, deck, the section east of the merge, J2's major road):
  `flyover_lanes`, `flyover_width_m`.

The west arterial has surface + flyover lanes; east of the merge the flyover lanes plus the single
J1 link lane (3.0 m, or the flyover width if that is narrower: it merges into a lane of that
width), which ends at the lane drop. The cross street (3.25 m) and J2's minor road (2.75 m) keep
their widths. The J1 turn rules are generated per approach and lane count (kerb lane left, middle
lanes through, last lane through and right; one lane does everything), J2's right turn enters the
median-side lane. The J1 box and J2 plate follow the widths by two rules taken from the default
layout (box half-height = max(kerb-lane centre + 6.75 m, link-lane centre + 10.25 m), which is 20 m
by default; J2's stop and exit lines at fixed rises above the kerb lane), which keep every turn
path longer than the longest vehicle (12 m) for all allowed structures.
Wider majors than 2 lanes per direction use HCM's four-lane critical gaps (the largest tabulated).
KPI detectors on the cross-street arms move inward when a wide structure shortens the arms.

*Evidence* (`tests/test_network_structures.py`, `tests/invariants/test_structures.py`): the default
structure reproduces the previous network **exactly** (fingerprint of every coordinate, id and
attribute, both J2 variants, taken from the pre-change code); every corner of the range (16) and
all 144 combinations of lanes {1..4}^2 x widths {2.5, 3.5, 4.0}^2 build, compile, route every
origin-destination pair, have consistent lanes/widths, no lateral overlap, correct clearance and
grade separation; the per-step invariants (no collision, no conflict-point overlap, conservation,
spillback guard, grade separation) hold on the **extremes (1 lane per group at 2.5 m, 4 lanes per
group at 4.0 m)** and on mixed combinations. Reference tables of a new structure are measured on
demand (about 5-8 s for the saturation flows, about 60 s for free-flow times in the background)
and cached on disk.

### Lane utilisation (does every open lane carry traffic?)

The 144-structure tests prove that routes *exist*; they never proved that vehicles *use* the lanes.
`tools/lane_utilisation.py` (`engine/utilisation.py`) runs a scenario and reports, for every lane and
every junction connector, the arrivals per hour **by transfer (insertion, link, connector) and by lane
change**, the mean number of vehicles on it (occupancy) and its share of its road's arrivals. A segment
is *unused* below 5 arrivals/h **and** an occupancy below 0.05 (both fixed before any result was seen).
For every unused segment the tool computes the cause from the route table, it does not guess:
`no_demand` (no origin-destination flow has a route that can reach it), `dead_lane` (routes enter the
lane, none leaves the road on it), `unexplained` (routes could use it and it carries nothing: a
lane-choice bug). Seed 1, 1,200 s, first 300 s excluded.

**Diagnosis (before any change).** The road under the flyover east of J1 was empty because **no flow
had a route over it**: W<->E trips take the flyover (the fastest route) and the cross street only had
N1<->S1 trips, so nothing was routed from the cross street onto the arterial. Of the causes listed in
the review request:

| Candidate cause | Verdict | Evidence |
|---|---|---|
| no demand / no OD pair passes there | **yes** (all 10 empty segments of the default) | route-table demand of `eb_surf_e`, `eb_e3:0`, `wb_surf_w` and their connectors is 0 veh/h |
| structural lanes without connectors downstream | no | every lane of every tested structure has a successor; adding the four flows below made all of them carry traffic, no structural change |
| spawning fills only some lanes | no | spawn shares on a plain 4-lane road 17/21/23/38 % at 1,200 veh/h (24-26 % at 3,000), 25 % each without bias; at the corridor entry lanes follow the route's good lanes and so the demand split |
| turn / ramp lane chosen too early, through lane stays empty | no evidence | with demand present (flyover closed) the through lanes are the busiest; no `unexplained` segment in any run |
| MOBIL keeps everyone out of a lane | **partly** | not behind the empty road, but a real lane-spread problem: the keep-left bias (0.2) is twice the MOBIL threshold, so the median lane of a plain road starved (below) |

Unused segments (of all lanes and connectors) before and after, same seed and window:

| Scenario | before | after (all listed exceptions) |
|---|---:|---:|
| default | 10 of 73 | 2 |
| rush hour | 10 of 73 | 2 |
| J2 one lane | 10 of 72 | 2 |
| 1 lane x 2.5 m per group | 9 of 53 | 2 |
| surface 3 lanes | 12 of 78 | 3 |
| surface 4 / flyover 3 lanes | 14 of 99 | 4 |
| 4 lanes x 4.0 m per group | 14 of 115 | 4 |
| flyover closed | 21 of 73 | 16 (the closed flyover and what only leads to it) |

**Three real bugs / design gaps found and fixed**

1. **No demand for the surface road east of J1** (above). The default demand now includes
   N1->E, S1->E, N1->W, S1->W at **60 veh/h each** (`CROSS_ARTERIAL_VEH_H`, 240 veh/h in total against
   600 veh/h of N1<->S1 traffic; a modest round value chosen before looking at KPIs, checked for no jam
   on seeds 1-4). Re-derived with the same rules as before: J1's critical flow ratio Y 0.649 -> **0.763**
   (the cross flows load the signals), rush hour = Y 0.85 reached with **x1.11** (was x1.31; rush hour now
   totals 4,345 veh/h, was 4,796), J2 minor demand 0.8 x measured capacity **234 veh/h left, 30 veh/h
   right** (was 214 / 37; `tools/measure_j2_capacity.py`: left 366, 312, 198, right 6, 96, 12 veh/h).
2. **A vehicle in a lane that does not lead onward could block that lane for ever.** The rule "no lane
   change within the stopping distance of a junction stop line" held a wrong-lane vehicle at the stop
   line (it cannot enter the junction, and could not leave its lane): with the extra flows, seed 4 jammed
   J2's eastbound lane 1 from t = 445 s (one vehicle stopped for more than 300 s). The rule now applies
   only to vehicles that can actually enter (`engine/mobil.py`); `tests/engine/test_stranded_vehicle.py`
   (it leaves in 3.1 s).
3. **Lane spreading: the keep-left bias.** See below.

**Exceptions: lanes and connectors that may carry nothing under the default demand**
(`engine/utilisation_exceptions.py`; `tests/test_lane_utilisation.py` fails on any other empty segment,
checks the list matches this one, and fails if a listed exception actually carries traffic):

| Key | What | Reason |
|---|---|---|
| `surface_through_at_j1` | the J1 surface through connectors W->E (`eb_surf_w:k>eb_surf_e:0`) and E->W (`wb_surf_e:0>wb_surf_w:k`) | the flyover is the fastest route for every W<->E trip, so no flow is routed through the signalised straight-ahead movement on the surface. They carry the W<->E traffic as soon as the flyover is closed (verified), so the exception applies only while it is open. With 3+ surface lanes the middle through lane feeds only this movement: it is not empty, but it carries only lane-change traffic (mean 0.1-0.4 vehicles) |
| `flyover_closed_structure` | ramps and deck of both directions | flyover closed (closed by definition) |
| `flyover_closed_approach_lanes` | lanes 2-3 of the 4-lane west road (they lead only to the closed ramp) and of its westbound exit (fed only by the ramp down) | flyover closed |

**Lane spreading and the keep-left bias.** MOBIL (Kesting et al. 2007) accepts a change toward the
median if its gain exceeds `threshold + bias` and toward the kerb if it exceeds `threshold - bias`
(left-hand traffic; threshold 0.1 m/s^2). With the original bias of 0.2 a change toward the kerb was
accepted at a *loss* of 0.1, and the median lane starved: occupancy shares on a plain road, kerb to
median, 4 lanes at 1,200 veh/h: **48/28/19/5 %**. Two behaviours bound the bias, both measured
(plain 3 km road, 300 veh/h per lane, seed 3, middle 1.2 km; overtake test: a car passes a truck that is
slower than it):

| bias [m/s^2] | car returns to the kerb lane after overtaking | 2 lanes | 3 lanes | 4 lanes |
|---:|---|---|---|---|
| 0.10 (= threshold) | **no, hogs the median lane** | 58/42 | 39/32/30 | 28/25/25/21 |
| 0.11 | yes, 45 s after passing | 59/41 | 43/33/23 | 33/26/24/17 |
| **0.12** | **yes, 40 s after passing** | **62/38** | **45/31/23** | **32/28/22/18** |
| 0.125 | yes | 63/37 | 45/32/23 | 36/27/23/**14** |
| 0.15 | yes | 67/33 | 51/30/19 | 40/28/22/**11** |
| 0.20 (before) | yes | 73/27 | 60/29/11 | 48/28/19/**5** |

A bias equal to the threshold would be the neat rule, but then the car that has just passed a truck makes
the truck behind it brake a little (politeness-weighted loss), the toward-kerb threshold is exactly 0, and
it never returns: it breaks `tests/engine/test_lane_changes.py` and is not realistic keep-left driving.
So the bias must *exceed* the threshold (0.11 is the smallest value on the 0.01 grid that returns) and
stay *small* (every lane at least 15 %: 0.125 already fails at 4 lanes). **0.12** satisfies both with a
margin and is the value used (`KEEP_LEFT_BIAS_MPS2`, with the rule next to it). It is bounded by two
behaviours, not fitted to a KPI; `tests/engine/test_lane_spread.py` (every lane of 2-4 at least 15 %,
kerb lane busiest) and the overtake test hold both bounds.

**Lane flow in the 3D view.** The "lane flow" button colours every lane and junction connector by its
measured flow (`engine/laneflow.py`: arrivals over the last 5 min, by transfer or lane change, scaled to
veh/h; a 60 s window would show a 56 veh/h lane as "unused" 40 % of the time by chance, 5 min only 0.9 %).
Magenta = unused (under 5 veh/h), then dark blue to teal, yellow and orange (1,200 veh/h and above).
Off by default; recoloured once a second; the legend states the scale.

### Building a scenario (off the event loop) and the table cache

A new session or reset is built in a worker thread: the server sends `building`, the other
sessions keep streaming, the session itself keeps answering pings, live changes are refused with
"still building", and the hello arrives when it is ready (a failed build sends an error and the old
simulation keeps running). Measured tables (saturation flows for a non-default vehicle mix or
structure, free-flow times) are stored in `backend/.cache/tables` keyed by the digest of every
input (the mix is part of it), so the same mix or structure is never measured twice on a machine,
and worker processes of a comparison reuse them (a "preparing" phase measures them once before
the runs start).

### Limits (each rejected with a message that names the limit)

WebSocket message at most 256 KB (`MAX_MESSAGE_BYTES`), at most 500 live changes per session or
document (`MAX_LIVE_CHANGES`), REST body at most 1 MB (`MAX_REQUEST_BYTES`, HTTP 413), a change
after the end of the run is an error, a failed or cancelled comparison keeps counting against the
job cap until its started runs have finished.

### Resets

The header's reset and the panel's "Reset with these settings" are the same action: the live
edits become the new initial settings, the structure draft applies, the seed is taken. A seed-only
`reset` message to the server behaves the same (it folds the live changes into the initial
settings).


### Vehicle frames

Format v2. Little-endian, struct-of-arrays, `12 + 9 n` bytes for `n` vehicles: a 12-byte
header (type, J1 phase and state, epoch, tick, count, speed index) and the columns `u16 id`,
`u16 segment`, `u16 s`, `i8 lateral`, `u8 speed`, `u8 flags` (brake light, class). A vehicle
is sent as *where it is on the lane graph*: the segment (an index into `hello.segments`, which
also lists each segment's id, length and successors), the arc length of its centre in 1 cm
steps, and a lateral offset in 5 cm steps. The browser places it on the real lane and
connector polylines from `GET /api/network`, so turns and ramps follow the curve at any
playback speed (v1 sent x, y, z, heading and pitch, 13 bytes, and the browser interpolated
straight lines between frames: up to 5.8 m of corner cutting for a frame pair spanning a
whole turn at 10x; now 1 mm). The model changes lanes instantaneously; the encoder blends a
lateral offset over 3 s for display only. The frontend renders 2 frame intervals behind the
newest frame and interpolates in simulation ticks along the lane graph, so motion is smooth
at any display rate and at 0.25x.

**Known display limitation:** during the 3 s lane-change blend a vehicle moves sideways
while its neighbours keep driving, so two vehicles can visually overlap by up to part of a
lane width. The simulation itself has no overlap (the no-collision invariant is on the model
state); only the drawing does.

Measured with `tools/measure_stream.py` at 10 frames/s: 159 vehicles 1,440 B raw per frame
(v1: 2,540 B for 178 vehicles), 412 B deflated; 548 vehicles 4,946 B raw, 1,081 B deflated.

### Streaming cost (measured on the wire)

`backend/tools/measure_wire.py` runs the real server, counts the bytes server to client
through a TCP proxy, and connects two clients with identical parameters at once, one with
permessage-deflate negotiated (what browsers do) and one without. Frames are sent at 10 Hz
at every speed of 1x or more. Totals include the KPI and stats messages (about 2.3 KB/s).

| vehicles | speed | compression | bytes per frame | bandwidth | per session-hour | hours per 5 GB |
|---|---|---|---|---|---|---|
| 178 | 1x | none | 2,540 | 25.5 KB/s | 92 MB | 54 |
| 178 | 1x | deflate | 736 | 7.4 KB/s | 27 MB | 187 |
| 676 | 1x | none | 8,982 | 90.3 KB/s | 325 MB | 15 |
| 676 | 1x | deflate | 4,564 | 46.0 KB/s | 165 MB | 30 |

Compression on the wire is only about 2x at 676 vehicles, much less than a stream that shares
compression context between frames would give. Offline analysis (not implemented, not
measured on the wire) at about 370 vehicles: each frame compressed alone 2,687 B (matches the
wire), compressed with shared context 1,147 B, delta-coded frames compressed alone 1,640 B and
with shared context 455 B. Server cost per session on the development machine: a simulation
step takes 1.8 ms at about 160 vehicles and 4.3 ms at about 640; encoding a frame takes
0.3 to 0.8 ms; a KPI snapshot takes 0.6 to 2.6 ms (once per second).

### Test commands

`pytest -m "not slow"` is the fast subset (about 40 s); `pytest` runs everything (about 7 min)
and is what CI runs. `backend/tools/` has the generators for the committed reference tables
(free-flow times, saturation flows) and the golden frame; the tests fail when a table is
stale and name the tool to run. `tools/lane_utilisation.py` prints the lane utilisation report
(above), `tools/compare_surface_lanes.py` reruns the surface-lane comparison.

Browser smoke tests (Playwright, `frontend/e2e/`, run in CI): from `frontend/`,
`npm run build && npm run e2e` (locally set `E2E_PYTHON` to the backend venv python and
`PW_CHANNEL=chrome` to use installed Chrome; CI installs Chromium). They load the app, switch
every preset (including the one-lane J2 layout), toggle the flyover, make live changes, change
lane counts and widths (the extremes) and reset, open the compare view and run a small
comparison; **any console error or uncaught page error fails a test**.

## Validation results

All numbers below are printed by the tests in `backend/tests/validation` and
`backend/tests/engine` (run with `pytest -s`). Parameters were not tuned to hit any target.

### Ring road: stop-and-go waves

Cars only, one lane, a 1 km ring, started in exact IDM equilibrium with one vehicle
disturbed to half speed; the last 5 of 15 simulated minutes are measured.

| density (veh/km) | mean speed (km/h) | speed sd across vehicles (km/h) | stopped | flow (veh/h) | wave speed (km/h) |
|---|---|---|---|---|---|
| 30 | 53.2 | 0.02 | 0% | 1,595 | (free flow) |
| 45 | 44.8 | 0.01 | 0% | 2,018 | (free flow) |
| 60 | 33.9 | 2.46 | 0% | 2,037 | −10.8 |
| 70 | 18.1 | 19.59 | 41% | 1,267 | **−14.4** |
| 80 | 14.1 | 18.03 | 52% | 1,125 | **−14.4** |

The disturbance dies out up to 45 veh/km and grows into stop-and-go from about 70 veh/km.
The jams travel **upstream at −14.4 km/h**, inside the empirically observed −10 to −20 km/h
range. Wave speed is the median shift of the space-time speed field maximising its circular
cross-correlation between frames 5 s apart (robust to several coexisting jams). The car
parameters are Treiber and Kesting's published city set (a = 1.0 m/s², T = 1.0 s,
b = 1.5 m/s², s0 = 2 m); an earlier set (a = 1.5, T = 1.2, b = 2.0) was string-stable at every
density and could not produce waves, which is why it was replaced.

### Give-way junction (J2): minor-road capacity against HCM

The original single shared minor lane was the main problem (see "Minor approach" below);
bunching of the major-road stream is at most a partial factor and is still a hypothesis.
The table is the measurement made before the lanes were split, for the minor *left* turn.
The minor road is saturated; vehicles accept a gap only if every priority vehicle is at
least the HCM critical headway (6.9 s) from the conflict point.

| conflicting flow | headway CV | usable gaps ≥ 6.9 s per hour | minor-left capacity | HCM c_p |
|---|---|---|---|---|
| 12 veh/h | 0.80 | 8 (12 if arrivals were random) | 880 veh/h | 1,072 veh/h |
| 896 veh/h | **1.42** | **40** (161 if random) | **156 veh/h** | 287 veh/h |

At high conflicting flow the minor-left capacity is about half of the HCM value. The
major-road stream is bunched (coefficient of variation 1.42 against 1.0 for random
arrivals) and long gaps are about four times rarer than a random-arrival assumption gives.
That is a measured property of the stream; that it *causes* the whole shortfall is not
shown, and the shared-lane blocking found later explains most of what the junction served.
The source of the bunching (the lane drop, the flyover merge or the upstream signal) has
not been isolated; that is a hypothesis, not a result.

The table above is for the minor *left* turn only. The *right* turn (to westbound) crosses
both eastbound lanes and merges into westbound lane 1, so it needs a 7.5 s gap in the
combined stream, and it had not been validated against HCM at all.

#### Minor approach: a left-turn lane and a right-turn lane

Originally the minor road had one lane shared by both turns. With the demo demand (about
1,230 veh/h conflicting with the right turn) the right-turn gap was open only 10% of the
time, so a waiting right-turner blocked the left-turners behind it even though the left
turn's gap was open 37% of the time: 48 veh/h served in total, against 216 veh/h from HCM's
own shared-lane formula for the same flows. This was the model working as designed, but a
single shared lane for two movements with such different gap needs is not how such a
junction is built. The approach now has two lanes (left lane, right lane; the stop line is
set back 3 m so that the left-turn path is longer than a truck). Evidence (see
`tests/engine/test_j2_minor_lanes.py`):

- with nobody entering from N2, every exit, lane change and junction entry on the whole
  network is **bit-identical** to the old network, with and without signals, so nothing
  outside J2's minor approach changed (every other connector's geometry is identical);
- left turns served in 10 minutes with a saturated right turn: **23** (27 with no right-turn
  demand) against **8** on the old shared lane;
- the right turn, now validated: with 980 veh/h conflicting flow HCM gives 207 veh/h and the
  simulation serves **132 veh/h (64%)**, never accepting a gap below the 7.5 s critical gap;
- default demo, 15 minutes: 17 vehicles starting at N2 complete their trip (7 before); the
  N2 queue peaks at 142 m (238 m before). The right-turn lane still queues (18 standing at the
  end): its demand of 100 veh/h exceeds what a movement crossing about 1,200 veh/h can serve.

### Known differences from HCM

**The J2 right turn serves 64% of HCM (132 against 207 veh/h at 980 veh/h conflicting).**
Nothing was tuned to close the gap. Attribution from the same run (saturated right turn):

1. *Fewer usable gaps than random arrivals (largest).* Gaps of at least 7.5 s occur 52 times
   per hour; a random stream of the same flow gives 127. The merged conflicting stream has a
   headway CV of 1.77 (1.0 for random). Where the bunching comes from is a hypothesis (the J1
   signal 1.1 km upstream, the lane drop and the flyover merge are candidates; not isolated).
2. *Partly offset:* in a bunched stream the gaps that do occur are longer, so each usable gap
   serves 2.5 vehicles against about 1.6 in HCM's formula.
3. *Follow-up headway:* consecutive right-turners enter 4.36 s apart (23 pairs) against
   HCM's 3.5 s; the right-turn path is 24.8 m long and curvature-limited to about 21 km/h,
   so each vehicle clears the conflict area more slowly. Worth up to about -20% for the
   second and later vehicles in a gap.
4. *Small:* a vehicle must be at the line when the window opens (2 of 15 windows unused;
   1.4 s from opening to the first entry).

Not a cause: the minor/minor conflicts (the two minor turns share none) and the critical
gap (never violated).

**Stop-line saturation flow is about 1,630 veh/h for cars, not 1,900.** It is measured,
not assumed: a standing queue of 24 vehicles is released and the headways after the fourth
vehicle are averaged. It decomposes (cars only, J1 through movement):

| experiment | flow (veh/h) |
|---|---|
| steady-state maximum on a ring at J1's desired speed (39 km/h) | 1,766 |
| J1 queue discharge, same parameters | **1,644** (93% of the steady maximum) |
| steady-state maximum on a ring at a 59 km/h desired speed | 2,074 |
| J1 queue discharge at a 60 km/h desired speed | 1,772 |
| the same, and a = 1.5 m/s² | 1,977 |

Two separate mechanisms explain the gap to HCM, and neither is the motorway "capacity drop":

1. **Desired-speed ceiling.** For IDM, steady flow is q(v) = v / (L + s\*(v)), and the
   (v/v0)⁴ term widens the equilibrium gap as v approaches the desired speed v0. With the
   40 km/h urban limit (39 km/h for a 3.5 m lane) the best steady flow is only about 1,766
   veh/h.
2. **Start-up transient.** A queue is released at a = 1.0 m/s² (a *comfortable* urban
   acceleration). The first four headways are 4.2, 3.1, 2.8 and 2.7 s against a steady
   2.15 s, and vehicles 5–24 cross the line at 29.5 km/h while still accelerating, so the
   discharge stays about 7% below the steady-state ceiling.

HCM's 1,900 comes from field data at higher speed limits with faster-accelerating drivers;
reproducing it needs both a higher desired speed and a ≈ 1.5 m/s², i.e. a different
parameter set. Sensitivities: a 1.0 → 1.5 gives +6%, T 1.0 → 1.2 gives −8%, v0 40 → 60 km/h
gives +8%. A genuine capacity drop (jam outflow below free-flow capacity) is a different
effect and appears on the ring road, not here. (An earlier commit message and test docstring
called the J1 discharge a "capacity drop"; that was wrong: it compared two different desired
speeds.)

### Signal controllers

`fixed_webster` (cycle from Webster's formula, inputs derived: ITE intergreens, measured
saturation flow) and `max_pressure` (Varaiya, the textbook rule). On the demo demand the
pure max-pressure controller switches every 8 s on average (62 greens in 15 minutes against
29 for Webster) and served slightly fewer vehicles (620 against 640): the textbook rule
ignores switching losses. It is kept as the baseline.

A second variant, `max_pressure_threshold`, is selectable beside it. Its two parameters were
**fixed before any controller comparison** (they are not tuned on results):

- minimum green 15 s (7 s for the textbook rule), the upper end of the 5–15 s range in the
  FHWA Signal Timing Manual;
- a switching threshold **derived from measured quantities**: a switch is made only if the
  best alternative phase beats the current one by the capacity a switch forfeits. At J1 a
  switch costs 6.4 s of intergreen plus 4.5 s of measured start-up loss (10.9 s), i.e. about
  4.1 vehicles of discharge at the mean measured saturation flow (1,346 veh/h).

Webster, pure max-pressure and thresholded max-pressure are to be compared over several
seeds and reported as a result. (One seed, 600 s, demo demand, for orientation only: 20, 40
and 23 greens; 375, 366 and 381 vehicles served.)

**Webster now uses the measured start-up loss.** The measured l1 at J1 is 3.8–5.5 s per
movement (HCM default 2 s); the plan uses the flow-weighted mean per phase. The extension of
effective green e = 2 s is still the HCM default (not measured). Before and after, default
demand: lost time L 25.5 s to **35.8 s**; unbounded Webster cycle C0 123.1 s to **167.1 s**;
applied cycle **120 s both times**, because C_MAX = 120 s (IRC:93) now limits it. The greens
therefore changed (displayed green = effective green + l1 - e): they now sum with the
intergreens to exactly the cycle (tested).

**Signal plans keep their design (a design decision).** When a scenario is built (at reset),
each signalised junction gets a *design record*: the measured saturation flows and start-up
losses **of the initial vehicle mix**, and the Webster plan **of the initial demand**. All three
controllers are built from it. A live change of the mix or the demand never touches it, exactly
as a real signal plan is timed by an engineer for a design mix and does not change when more
trucks show up. Switching the policy live starts the design plan (or the design saturation
flows) from the current phase; Webster is recomputed only at the next reset. Test:
`tests/engine/test_live_changes.py` (a 50% truck mix change leaves flows, losses and greens
unchanged; a reset with that mix recomputes them). The editor says so next to the mix inputs.

## A/B comparison (Compare tab)

Pick scenario A and B (a preset, the editor's current settings, or an imported JSON file),
3, 5 or 10 runs, a duration and a warm-up. The backend runs every (scenario, seed) headless,
in a process pool, with no WebSocket frames, and reports for each metric the mean of A, the
mean of B, the difference **B - A** and its 95% confidence interval, with the per-seed values
one click away. If the interval includes zero the table says "NOT significant with N runs".

**Paired runs.** Run *i* of A and of B use the same seed `base + i`. Arrivals (time, class,
destination) are drawn from the `spawn`, `vehicle_class` and `route` streams *when a vehicle
is generated*, never when it is inserted, and no stream is used for driver behaviour, so with
the same demand and mix A and B receive identical arrivals whatever the signals, flyover or
lane layout (`tests/engine/test_runmetrics.py` compares the arrival lists of four variants).
If A and B differ in demand or mix the result says "arrivals are not paired".

**Warm-up (default 300 s, configurable).** The longest free-flow trip in the network is 242 s,
so by 300 s the first vehicles have left and every route carries traffic. Statistics use the
window [warm-up, duration) only.

**Cohort rule for trips that cross the warm-up boundary.** Trip-level metrics (delay, travel
time, flyover share) use the vehicles *generated at or after the warm-up end* that *had at
least their own free-flow trip time left before the end* (a vehicle generated a minute before
the end cannot have finished and would count as "zero delay"). The second condition depends
only on the generation time and the route, never on the outcome, so it treats A and B alike;
excluded vehicles are counted ("too young") and still appear in throughput and unserved
demand. Throughput is a flow: completed trips that *exit* inside the window.

**Unfinished trips are counted, not dropped.** The primary metric, **mean delay**, covers
every cohort vehicle. A completed trip contributes its measured delay
`(t_exit - t_generated) - free_flow(origin, destination, class)` (waiting in the entry queue
included; the free-flow time is the engine-measured time of the fastest route on the fully
OPEN network for that origin and destination, whatever route the vehicle took, so a detour
forced by a closure counts as delay). A vehicle still in the network or still waiting
at an entry at the end contributes the lower bound `max(0, (t_end - t_generated) - free_flow)`:
its final delay can only be larger. Dropping them would flatter the scenario that traps more
vehicles. Always shown beside it: delay of completed trips only, and the numbers of completed
and unfinished trips. Travel-time percentiles cover completed trips only (so p90 is biased
low for the worse scenario).

| Metric | Definition |
|---|---|
| mean delay (primary) | above; seconds per cohort vehicle |
| mean delay, completed only | cohort trips that finished |
| travel time p50 / p90 | `t_exit - t_generated` of completed cohort trips, linear-interpolated percentiles |
| throughput | completed trips with `t_exit` inside the window, per hour |
| unserved demand | vehicles waiting in entry queues at the end |
| unfinished trips | cohort vehicles not finished at the end (in network or waiting) |
| queue (J1: 4 approaches, J2: 3) | the existing queue measurement: a vehicle is queued below 5 mi/h (2.2 m/s), the queue is the unbroken chain from the stop line whose links are at most 7.0 m (the largest IDM crawling gap, derived), length = stop line to the rear of the last vehicle, per approach the longest lane; sampled every 1 s inside the window; per junction the *longest approach queue*, reported as its maximum and its time average |
| flyover share | of completed cohort trips whose OD pair's open-network fastest route uses the flyover (W-E, E-W, W-N2, N2-W), the share that travelled on the deck; a closure gives 0 and the denominator is the same in A and B |

**Statistics.** With d_i = B_i - A_i over the n paired seeds, the interval is
`mean(d) +- t(0.975, n-1) * sd / sqrt(n)` with df = n-1 (t = 4.303, 2.776, 2.262 for 3, 5, 10
runs). The Student-t quantile is computed in `engine/pairedstats.py` and tested against
`scipy.stats.t.ppf`, `scipy.stats.ttest_rel` and a worked example. Runs where a metric is
undefined are dropped from that metric only and the table says so. If every seed shows the *same* non-zero
difference (no variance) there is no meaningful interval and no p-value: the table says "constant
difference across seeds, no variance, the confidence interval isn't meaningful" (never p = 0 or
"significant"). About a dozen metrics are
compared at once with unadjusted intervals, so a single "significant" among them should be
read with care. Overloaded scenarios (queues that keep growing) do not settle, so their numbers
depend on how long they are run: the duration, warm-up and demand are shown with every result.

**Server cost and limits.** Jobs run in a background process pool with a progress bar; at most
`COMPARE_MAX_JOBS` (default 1) run at once, further requests get HTTP 429; `COMPARE_MAX_RUNS`
(10), `COMPARE_MAX_DURATION_S` (1800) and `COMPARE_WORKERS` (default min(4, cores-1)) restrict
a hosted server; invalid requests are errors, never clamped. Finished runs are cached on disk
by a hash of (scenario document, seed, duration, warm-up, metric definition version, model
digest, and a hash of the engine and network source files with line endings normalised, so
changing engine logic invalidates old entries), so the same comparison never runs twice and comparisons that share runs pay once.
The two built-in experiments are precomputed (`tools/gen_experiments.py`, stored in
`trafficsim/data/experiments/`, stale when the model digest changes) and served instantly.

### Built-in experiments (10 paired runs, seeds 1-10, 900 s, warm-up 300 s, rush-hour demand)

Parameters were fixed before any result was seen. Rush hour is every default flow x1.11
(4,345 veh/h in total; J1 critical flow ratio 0.847). All figures are in the Compare tab
(stored results, served instantly); the tables below are generated from the same files.
Everything that is not significant is shown.

**Reading the tables.**
- *Signal policy.* Thresholded max-pressure and Webster are **not distinguishable on the primary
  metric** (mean delay -0.9 s, interval [-4.6, +2.8] crosses zero), nor on completed-trip delay,
  p90, throughput or unfinished trips. The secondary metrics that do differ point one way: the
  thresholded rule has a slightly lower p50 (-1.0 s) and longer J1 queues (maximum +17.5 m,
  average +7.4 m); with a dozen metrics compared at once these three "significant" ones should be
  read with care. Pure max-pressure is clearly worse than both (delay +24.6 s against Webster,
  throughput -368 veh/h, J1 queue maximum +97 m); this is the textbook rule's switching loss
  showing up (it switches every ~8 s). The J2 rows are **not significant** for any policy pair:
  W<->E trips reach J2 over the flyover, which bypasses J1, and the cross-street trips that now
  also reach J2 over the surface road are too few (240 veh/h) for J1's policy to move J2's queues
  measurably. (Before the cross-street <-> arterial flows were added these rows were *identical in
  every run*, because nothing that reached J2 passed J1. The unserved-demand row is still identical.)
- *Flyover.* Closing the flyover at rush hour overloads J1 and the scenario does not settle in
  900 s. Mean delay rises by 165 s and 416 more vehicles per run are unfinished (delay is measured
  against the open-network route, so the detour itself is part of it), and 68 vehicles per run
  are still waiting at the entries at the end. Beware the travel-time rows of the closed case: only
  60 of its 527 cohort trips complete (the short ones), so its p50 is *lower* than the open case's
  and its p90 interval is wide; that is survivorship, not a benefit, which is why the unfinished
  count and the lower-bound delay sit beside them. The westbound surface queue grows back past J2
  (J2 longest approach queue maximum +125 m). Flyover share of the closed case is undefined: no
  eligible long trip completes in any seed.
- *Changes since the first publication of these tables* (the lane utilisation round): rush hour is
  x1.11 of a default demand that now includes the cross-street <-> arterial flows (it was x1.31 of
  the old one), the keep-left bias is 0.12 (was 0.2), a vehicle in a lane that does not lead onward
  can leave it at the stop line. The conclusions about the policies and the flyover are the same;
  the numbers are not (for example max-pressure against Webster: delay +20.9 s then, +24.6 s now).

#### Signal policy at rush hour

Webster (fixed-time) against pure max-pressure and thresholded max-pressure at J1, rush-hour demand (every flow x1.11). Difference = B - A.

**Webster vs max-pressure** (A = Webster, B = Max-pressure; 10 paired runs, seeds 1-10, 900 s, warm-up 300 s, demand 4345 veh/h; per run, mean cohort A 527 (476 completed, 51 unfinished), B 527 (414 completed, 114 unfinished))

| Metric | A | B | B - A | 95% CI of B - A | Verdict |
|---|---:|---:|---:|---:|---|
| Mean delay, all trips (unfinished: lower bound) [s] | 39.6 | 64.2 | +24.6 | [+21.1, +28.0] | **significant** |
| Mean delay, completed trips only [s] | 36.8 | 45.5 | +8.7 | [+5.1, +12.3] | **significant** |
| Travel time p50 (completed) [s] | 184.9 | 185.7 | +0.9 | [+0.2, +1.5] | **significant** |
| Travel time p90 (completed) [s] | 231.1 | 253.2 | +22.0 | [+6.6, +37.4] | **significant** |
| Throughput (completed trips in window) [veh/h] | 4138 | 3769 | -368 | [-424, -312] | **significant** |
| Unserved demand (waiting at entries at the end) [veh] | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | identical in every run |
| Unfinished trips (cohort, at the end) [veh] | 50.9 | 113.7 | +62.8 | [+54.8, +70.8] | **significant** |
| J1 longest approach queue, maximum [m] | 100.7 | 197.6 | +97.0 | [+76.3, +117.6] | **significant** |
| J1 longest approach queue, time average [m] | 58.0 | 103.5 | +45.4 | [+37.4, +53.5] | **significant** |
| J2 longest approach queue, maximum [m] | 63.8 | 65.4 | +1.6 | [-8.6, +11.9] | not significant |
| J2 longest approach queue, time average [m] | 27.1 | 26.1 | -1.1 | [-4.5, +2.3] | not significant |
| Flyover share of eligible trips [ratio] | 1.000 | 1.000 | 0.000 | [0.000, 0.000] | identical in every run |

**Webster vs thresholded max-pressure** (A = Webster, B = Thresholded max-pressure; 10 paired runs, seeds 1-10, 900 s, warm-up 300 s, demand 4345 veh/h; per run, mean cohort A 527 (476 completed, 51 unfinished), B 527 (475 completed, 52 unfinished))

| Metric | A | B | B - A | 95% CI of B - A | Verdict |
|---|---:|---:|---:|---:|---|
| Mean delay, all trips (unfinished: lower bound) [s] | 39.6 | 38.7 | -0.9 | [-4.6, +2.8] | not significant |
| Mean delay, completed trips only [s] | 36.8 | 35.3 | -1.5 | [-4.8, +1.9] | not significant |
| Travel time p50 (completed) [s] | 184.9 | 183.9 | -1.0 | [-2.0, -0.0] | **significant** |
| Travel time p90 (completed) [s] | 231.1 | 238.6 | +7.5 | [-0.4, +15.5] | not significant |
| Throughput (completed trips in window) [veh/h] | 4138 | 4108 | -30 | [-70, +10] | not significant |
| Unserved demand (waiting at entries at the end) [veh] | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | identical in every run |
| Unfinished trips (cohort, at the end) [veh] | 50.9 | 51.9 | +1.0 | [-4.8, +6.8] | not significant |
| J1 longest approach queue, maximum [m] | 100.7 | 118.2 | +17.5 | [+6.3, +28.6] | **significant** |
| J1 longest approach queue, time average [m] | 58.0 | 65.4 | +7.4 | [+1.3, +13.5] | **significant** |
| J2 longest approach queue, maximum [m] | 63.8 | 66.5 | +2.7 | [-11.7, +17.1] | not significant |
| J2 longest approach queue, time average [m] | 27.1 | 27.1 | -0.1 | [-5.6, +5.5] | not significant |
| Flyover share of eligible trips [ratio] | 1.000 | 1.000 | 0.000 | [0.000, 0.000] | identical in every run |

**Max-pressure vs thresholded max-pressure** (A = Max-pressure, B = Thresholded max-pressure; 10 paired runs, seeds 1-10, 900 s, warm-up 300 s, demand 4345 veh/h; per run, mean cohort A 527 (414 completed, 114 unfinished), B 527 (475 completed, 52 unfinished))

| Metric | A | B | B - A | 95% CI of B - A | Verdict |
|---|---:|---:|---:|---:|---|
| Mean delay, all trips (unfinished: lower bound) [s] | 64.2 | 38.7 | -25.5 | [-27.7, -23.3] | **significant** |
| Mean delay, completed trips only [s] | 45.5 | 35.3 | -10.2 | [-11.9, -8.5] | **significant** |
| Travel time p50 (completed) [s] | 185.7 | 183.9 | -1.9 | [-2.7, -1.0] | **significant** |
| Travel time p90 (completed) [s] | 253.2 | 238.6 | -14.5 | [-25.4, -3.6] | **significant** |
| Throughput (completed trips in window) [veh/h] | 3769 | 4108 | +338 | [+316, +361] | **significant** |
| Unserved demand (waiting at entries at the end) [veh] | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | identical in every run |
| Unfinished trips (cohort, at the end) [veh] | 113.7 | 51.9 | -61.8 | [-67.2, -56.4] | **significant** |
| J1 longest approach queue, maximum [m] | 197.6 | 118.2 | -79.5 | [-98.2, -60.7] | **significant** |
| J1 longest approach queue, time average [m] | 103.5 | 65.4 | -38.1 | [-44.0, -32.1] | **significant** |
| J2 longest approach queue, maximum [m] | 65.4 | 66.5 | +1.1 | [-11.7, +14.0] | not significant |
| J2 longest approach queue, time average [m] | 26.1 | 27.1 | +1.0 | [-3.9, +5.9] | not significant |
| Flyover share of eligible trips [ratio] | 1.000 | 1.000 | 0.000 | [0.000, 0.000] | identical in every run |

#### Flyover open vs closed at rush hour

The flyover open against closed from the start, rush-hour demand. Difference = closed - open.

**Flyover open vs closed** (A = Flyover open, B = Flyover closed; 10 paired runs, seeds 1-10, 900 s, warm-up 300 s, demand 4345 veh/h; per run, mean cohort A 527 (476 completed, 51 unfinished), B 527 (60 completed, 467 unfinished))

| Metric | A | B | B - A | 95% CI of B - A | Verdict |
|---|---:|---:|---:|---:|---|
| Mean delay, all trips (unfinished: lower bound) [s] | 39.6 | 204.3 | +164.7 | [+159.4, +170.0] | **significant** |
| Mean delay, completed trips only [s] | 36.8 | 101.8 | +65.0 | [+33.1, +96.9] | **significant** |
| Travel time p50 (completed) [s] | 184.9 | 108.3 | -76.6 | [-83.5, -69.6] | **significant** |
| Travel time p90 (completed) [s] | 231.1 | 441.6 | +210.5 | [+119.8, +301.2] | **significant** |
| Throughput (completed trips in window) [veh/h] | 4138 | 1730 | -2407 | [-2491, -2324] | **significant** |
| Unserved demand (waiting at entries at the end) [veh] | 0.0 | 68.0 | +68.0 | [+51.1, +84.9] | **significant** |
| Unfinished trips (cohort, at the end) [veh] | 50.9 | 467.1 | +416.2 | [+407.9, +424.5] | **significant** |
| J1 longest approach queue, maximum [m] | 100.7 | 381.1 | +280.4 | [+267.0, +293.7] | **significant** |
| J1 longest approach queue, time average [m] | 58.0 | 237.4 | +179.4 | [+172.5, +186.3] | **significant** |
| J2 longest approach queue, maximum [m] | 63.8 | 188.4 | +124.6 | [+87.0, +162.2] | **significant** |
| J2 longest approach queue, time average [m] | 27.1 | 29.5 | +2.4 | [-9.0, +13.7] | not significant |
| Flyover share of eligible trips [ratio] | 1.000 | - | - | - | undefined (no usable pair) |

### Example: structure comparisons (rush hour, 10 paired runs, 900 s, warm-up 300 s)

Run with the comparison service (`tools/compare_structures.py`); the reference tables of the two
new structures are measured once in a "preparing" phase (about 75 s), the 20 runs took 571 CPU s
(230 s wall on 4 workers).

**Surface road: 3 lanes x 3.5 m (A) against 2 lanes x 2.75 m (B)**, flyover group unchanged, rush hour.
The first run of this comparison showed "almost no effect"; the lane utilisation report then showed
that the surface road carried no through traffic at all. So it was rerun, and since two things changed
(the demand and the keep-left bias) in a 2 x 2 design, `tools/compare_surface_lanes.py`: 10 paired runs
(seeds 1-10, 900 s, warm-up 300 s) per column, difference B - A with its 95 % paired interval
(* = interval excludes zero). The column "reproduced" is the old setting run with today's code (it
includes the stop-line fix); the first column is the result as first published.

| B - A | first published | old demand, bias 0.2 (reproduced) | old demand, bias 0.12 | new demand, bias 0.2 | **new demand, bias 0.12 (now)** |
|---|---|---|---|---|---|
| mean delay [s] | -0.7 [-1.6, +0.2] | -0.6 [-1.5, +0.3] | -0.8 [-1.9, +0.3] | -0.8 [-1.6, -0.1] * | **-1.2 [-2.5, +0.1]** |
| throughput [veh/h] | 0 [-21, +21] | -2.4 [-23.3, +18.5] | +7.8 [-11.6, +27.2] | +25.2 [+0.5, +49.9] * | **+18.6 [-7.0, +44.2]** |
| unfinished trips | -0.6 [-4.2, +3.0] | -0.2 [-3.7, +3.3] | -1.9 [-5.7, +1.9] | -2.1 [-4.8, +0.6] | **-2.4 [-5.3, +0.5]** |
| J1 queue, maximum [m] | -4.6 [-12.2, +2.9] | -5.3 [-12.8, +2.2] | -8.0 [-19.0, +2.9] | -3.1 [-11.4, +5.1] | **-3.9 [-13.5, +5.7]** |
| J1 queue, time average [m] | -2.7 [-4.2, -1.1] * | -2.3 [-3.9, -0.7] * | -3.3 [-6.7, +0.1] | -3.3 [-6.2, -0.4] * | **-2.7 [-6.7, +1.3]** |
| travel time p50 [s] | +0.5 [+0.1, +0.9] * | +0.5 [+0.1, +0.8] * | +0.6 [+0.2, +0.9] * | +0.4 [+0.1, +0.8] * | **+0.5 [+0.2, +0.8]** * |

**Was "almost no effect" real, or were the extra lanes unused? Real, and now explained.** The old result
is reproduced (column 2), and none of the four settings shows an effect of practical size (mean delay
within about 1 s of zero; the two intervals that exclude zero in the new-demand/old-bias column, delay
-0.8 s and throughput +25 veh/h, are small and disappear with the final bias). The extra lane is not
unused because of a bug: with 3 surface lanes the approach has a left lane, a through-only lane and a
through-and-right lane, and the through movement has no demand (the flyover takes it). Utilisation of
A's surface lanes (seed 1, arrivals per hour and mean vehicles on the lane): kerb/left lane 270 and
6.7, middle through lane 180 and **0.2** (lane-change transit only), right lane 138 and 3.0; with the old
demand and bias 312 / 6.3, 204 / 0.2, 186 / 3.7. Both structures have the same left and right turn
lanes, so the third lane adds no capacity for any demand that exists. The surface lane count would
matter when the surface carries through traffic (flyover closed, or a flyover that cannot take it);
that case was not tested here. The overall level of delay is lower with the new demand (40 s against 46 s mean
delay in A), where the rush-hour factor is also smaller (x1.11, 4,345 veh/h against 4,796); the
comparison of A and B within a column is what this table is about.

**Flyover group: 2 lanes (A) against 1 lane (B)**, surface road unchanged: a large effect. Mean
delay +90.5 s [+76.7, +104.4], throughput -944 veh/h [-1,126, -763], unserved demand +311 vehicles,
unfinished trips +203, p50 travel time (completed trips only, survivorship-biased) +139 s. J1's
queue is *shorter* (-14 m maximum, -9 m average) because less traffic reaches it.

### CPU cost of a comparison (measured, `tools/gen_experiments.py`, 4 worker processes)

| Comparison | runs | CPU time | wall time |
|---|---:|---:|---:|
| 10 runs x 2 scenarios, 900 s, default demand | 20 | 572 s (28.6 s per run) | 150 s |
| 10 runs x 2 scenarios, 900 s, rush-hour demand | 20 | 649 s (32.4 s per run) | 171 s |

A run costs about 3% of the simulated time in CPU (28-32 s for 900 s). On a single core a
10-run comparison is about 10 CPU-minutes; on the 0.1-CPU Render tier it would take over an hour
and a half, which is why the built-in experiments ship precomputed and custom comparisons are
limited by configuration (`COMPARE_MAX_RUNS`, `COMPARE_MAX_DURATION_S`, `COMPARE_MAX_JOBS`).

## Project rules

See [CLAUDE.md](CLAUDE.md) for module boundaries, units, the invariants that the tests
enforce, and the code rules.
