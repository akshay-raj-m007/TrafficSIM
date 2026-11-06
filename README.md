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

> Status: **step 2a done** (vehicle physics, junction control, signals and validation in the
> engine); **step 2b in progress** (vehicles and KPIs in the browser). Scenario controls come in
> step 3. Deployment is parked: this runs on localhost.

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
| `WS /ws/sim` | live session: `hello`, then `tick` frames; accepts `set_speed`, `reset`, `ping`. Returns `busy` and close code 1013 when full |

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

### Give-way junction (J2): platooned major-road traffic offers fewer gaps than HCM assumes

The minor road is saturated; vehicles accept a gap only if every priority vehicle is at
least the HCM critical headway (6.9 s) from the conflict point.

| conflicting flow | headway CV | usable gaps ≥ 6.9 s per hour | minor-left capacity | HCM c_p |
|---|---|---|---|---|
| 12 veh/h | 0.80 | 8 (12 if arrivals were random) | 880 veh/h | 1,072 veh/h |
| 896 veh/h | **1.42** | **40** (161 if random) | **156 veh/h** | 287 veh/h |

At high conflicting flow the minor-left capacity is about half of the HCM value because the
major-road stream is bunched (coefficient of variation 1.42 against 1.0 for random
arrivals), so long gaps are about four times rarer than HCM's random-arrival assumption
implies. Capacity is therefore a property of the *arrival process* here, not just of the
flow. The source of the bunching (the lane drop, the flyover merge or the upstream signal)
has not been isolated yet; that is a hypothesis, not a result.

### Known differences from HCM

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

Note: the measured start-up loss at J1 is 3.8–5.5 s per movement against the HCM default
l1 = 2 s used in the Webster lost-time sum.

## Project rules

See [CLAUDE.md](CLAUDE.md) for module boundaries, units, the invariants that the tests
enforce, and the code rules.
