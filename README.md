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
| `GET /api/network` | the network geometry (metres; x east, y north, z up) |
| `WS /ws/sim` | live session. Server to client: `hello` (class sizes, frame format, KPI definitions), binary vehicle frames (only when the simulation advanced), `kpi` and `stats` (once per second), `busy`. Client to server: `set_speed` (0, 0.25, 0.5, 1, 2, 5, 10), `reset`, `ping`. Close code 1013 when full. Optional query parameters `seed`, `signal` (`fixed_webster`, `max_pressure`, `max_pressure_threshold`, `uncontrolled`) and `demand_scale` (0.25 to 3) are an experiment seam; there is no UI for them yet |

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
stale and name the tool to run.

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
intergreens to exactly the cycle (tested). The fixed-time plan is computed from the demand in
force when it is selected and does not follow later demand changes (that is what fixed-time
means).

## Project rules

See [CLAUDE.md](CLAUDE.md) for module boundaries, units, the invariants that the tests
enforce, and the code rules.
