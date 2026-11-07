# TrafficSIM — project rules for Claude

## Goal
An agent-based traffic simulator that feels like a small **research workbench**, not a toy.
A Python/NumPy engine (IDM car-following + MOBIL lane changes) runs a hand-built road
network (two junctions, a flyover with ramps, 1/2/3/4-lane roads, a 3→2 lane drop,
turning movements). It is served by FastAPI: each browser session gets its own simulation
streamed over a WebSocket at 10 Hz, and headless A/B comparisons run over REST. The frontend
(Vite + React + Three.js) shows a true metric 3D view with scenario controls and measured
telemetry. Built for the QUEST Lab pre-doctoral application.

## Module boundaries (enforced by `backend/tests/test_boundaries.py`)
| Package | May import | Must never import |
|---|---|---|
| `backend/trafficsim/engine/` | stdlib, `numpy`, `trafficsim.engine`, `trafficsim.network` | fastapi, pydantic, server code |
| `backend/trafficsim/network/` | stdlib, `numpy`, `trafficsim.network`, `trafficsim.engine` | fastapi, pydantic, server code |
| `backend/trafficsim/server/` | anything above + fastapi/pydantic/uvicorn | — (adapter layer only) |
| `frontend/src/` | talks to the backend only via HTTP/WS JSON | — |

- The **backend is the single source of truth for the network geometry** (`GET /api/network`).
  The frontend never keeps its own copy of the roads.
- Engine/network code must stay usable from plain Python (pytest, offline parameter sweeps).

## Units, axes, time
- **1 unit = 1 metre everywhere.** No visual scaling factors on road widths, lane offsets or
  vehicle sizes. Ribbons are built from exact `width_m`; tests enforce this
  (`frontend/src/scene/ribbon.test.ts`, `backend/tests/test_network_demo.py`).
- Engine axes: **x east, y north, z up**. Three.js axes: y up. The *only* conversion is
  `frontend/src/scene/coords.ts`: three(x, y, z) = (sim.x, sim.z, −sim.y), scale 1.
- **Left-hand traffic (India).** Lane index 0 = kerb lane (leftmost in direction of travel);
  higher indices go toward the median. Flyover diverges from the median-side lanes.
- **Fixed time step `DT = 0.1 s`** (`engine/constants.py`), never configurable per scenario.
  The clock is an integer `tick`; `t = tick / STEPS_PER_SECOND` (no accumulated floats).
  Sim stepping is decoupled from rendering; the renderer interpolates between sim states.

## Hard invariants (each has an automated test; never break them)
1. **Determinism** — same seed + scenario ⇒ identical trajectories and KPIs.
   `tests/invariants/test_determinism.py`. Use named `SeedSequence.spawn` streams
   (`engine/rng.py`); never iterate over `set`s; avoid transcendental ufuncs in hot paths
   (write `x*x*x*x`, not `np.power(x, 4)`); no wall-clock time inside the engine.
2. **No collisions, no negative speeds** — gap > 0 and v ≥ 0 at every step.
   `tests/invariants/test_no_collision.py`. Never "fix" a collision by teleporting.
3. **Spillback guard** — no vehicle enters a junction unless the exit lane has room for it.
   `tests/invariants/test_spillback.py`. Precisely: at the moment a vehicle commits to
   entering (its last chance to stop comfortably, `engine/gates.py`), the *guaranteed*
   room on its exit lane — up to where the last vehicle there would stop at its
   comfortable deceleration, minus space of vehicles that enter first — is at least its
   length + s0. Outcome check: zero vehicle-seconds held up inside junction boxes.
4. **Conservation** — spawned = active + exited; blocked spawns are counted as unserved
   demand, never silently dropped. `tests/invariants/test_conservation.py`.
5. **Grade separation** — a flyover vehicle can never interact with or turn onto the road
   below except via the defined ramps. `tests/invariants/test_grade_separation.py`.

## Modelling honesty
- KPIs are **measured, not estimated**: flow from detector lines, queue length from actual
  vehicle positions, delay = actual − free-flow travel time (per class, per route).
  If something can't be measured properly, leave it out. No fudge factors.
- Approximations are labelled honestly (e.g. the lane-width speed model is not called "HCM"
  unless the real HCM adjustment is implemented). Two-wheelers do not filter between lanes.

## Code rules
- Each source file stays under **~200 lines** (ESLint `max-lines`; `tests/test_file_length.py`).
- Tests: **pytest** for the engine/server, **Vitest** for the frontend.
- Commit after each working step with a clear message.

## Commands
```bash
# Backend (from backend/)
py -3.12 -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -m "not slow"  # fast subset (~45 s): use after every change
.venv/Scripts/python -m pytest              # all tests (~5 min); CI runs this
# tests over ~5 s carry @pytest.mark.slow; tests/test_fast_subset.py keeps every area covered
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m uvicorn trafficsim.server.app:app --reload --port 8000

# Frontend (from frontend/)
npm ci
npm run dev        # Vite on :5173, proxies /api and /ws to :8000
npm run lint && npm test && npm run build

# Single-origin Docker image (from repo root)
docker build -t trafficsim . && docker run --rm -p 8000:8000 trafficsim
```

## Deployment
Render free tier (Docker runtime, `render.yaml`): 0.1 CPU, 512 MB, sleeps after 15 min idle,
5 GB/month egress. Hence: single uvicorn worker, `MAX_SESSIONS` cap (default 2) with a
"server busy" message, and compact binary WS frames once vehicles are streamed.

## Step 2b additions
- **Workflow:** after a part is built and tested, commit and push, then rebuild the
  frontend (`npm run build` in `frontend/`) and restart uvicorn so localhost shows it.
- **Committed reference tables** (digest of every input; tests fail when stale):
  `backend/trafficsim/data/freeflow_demo.json` (`python tools/gen_freeflow.py`, ~80 s) and
  `calibration_demo.json` (`python tools/gen_calibration.py`, ~8 s). Any change to the lane
  graph, vehicle classes or a model constant makes both stale: regenerate and commit.
- **Golden frame:** `python tools/gen_golden_frame.py` rewrites the fixtures in
  `frontend/src/api/fixtures/`; the Python and TypeScript decoders must both read them.
- **Measurement tools:** `tools/measure_stream.py` (frame size/CPU), `tools/measure_wire.py`
  (real bytes on the wire, with and without compression).
- **Wire protocol:** binary vehicle frames (`server/frames.py`, `12 + 9 n` bytes, lane-graph placement (segment, arc length, lateral)) plus JSON
  `hello` / `kpi` / `stats`. Speeds 0, 0.25, 0.5, 1, 2, 5, 10. The renderer interpolates in
  simulation ticks (`frontend/src/scene/interpolator.ts`), 2 frame intervals behind.
- **Signal controllers:** `fixed_webster`, `max_pressure` (textbook), `max_pressure_threshold`
  (15 s minimum green, switching threshold derived from the lost time of a switch; fixed
  before any comparison, not tunable on results).


## Step 3 / 4a additions
- **Live changes** (`engine/changes.py`, `Simulation.schedule`/`change_log`): demand, mix, J1 policy,
  flyover open/closed, applied at a tick boundary and logged; same seed + same log = same run
  (`tests/engine/test_live_changes.py`). Closing the flyover re-routes what can still choose and
  grandfathers vehicles too close to the diverge (README).
- **Scenario JSON** (`server/scenario_doc.py`, version 1): validated, no clamping, errors with paths;
  presets in `server/presets_doc.py`; J2 default demand from measured capacities
  (`tools/measure_j2_capacity.py`).
- **Frame format v2**: vehicles sent as (segment, arc length, lateral), placed on the lane graph in
  the browser (`frontend/src/scene/laneGeometry.ts`); fixtures from `tools/gen_golden_frame.py`.
- **A/B comparison**: metrics `engine/runmetrics.py` (definitions in the README), paired t
  `engine/pairedstats.py` (checked against SciPy), service `server/compare_*.py` (process pool,
  per-run cache in `backend/.cache/compare`, job cap, limits via env). Built-in experiments are
  committed in `trafficsim/data/experiments/`; they go stale when the model digest or
  `METRICS_VERSION` changes: regenerate with `python tools/gen_experiments.py` (about 15 min on 4
  cores). Committed tables now come in two variants (J2 minor approach 2 lanes / 1 lane):
  `python tools/gen_freeflow.py` and `tools/gen_calibration.py` write both.
- Frontend: `npm run build` after changes; Prettier style is single quotes, 100 columns.

## Lane utilisation round
- **Rule:** under the default demand every lane and junction connector open to traffic carries
  vehicles, except those listed with a reason in `engine/utilisation_exceptions.py` (and in the
  README, "Lane utilisation"). `tests/test_lane_utilisation.py` fails on an unlisted empty one, for
  the default structure and the extremes. Report tool: `python tools/lane_utilisation.py`
  (`engine/utilisation.py`: arrivals/h by transfer and by lane change, occupancy, share, computed cause).
- **Default demand** now includes N1/S1 -> E/W (60 veh/h each): without them the surface road east of J1
  had no demand. J2 minor demand, J1 Y (0.763) and the rush factor (x1.11) were re-derived with the same rules.
- **Keep-left bias** `KEEP_LEFT_BIAS_MPS2` = 0.12: must exceed the MOBIL threshold (else an overtaker
  never returns to the kerb lane) and stay small (else the median lane starves); evidence in the README.
- **Lane flow overlay:** `engine/laneflow.py` (arrivals per segment over 5 min) -> `kpi.lane_flow` -> a
  "lane flow" toggle in the 3D view (`frontend/src/scene/laneFlow.ts`, `flowColor.ts`).

## Step 4b: results made visible
- **Charts** (results drawer): `engine/charts.py` measures (Edie) the network MFD, a 10 m x 1 s speed field of four
  corridors (surface/flyover x eastbound/westbound) and J1/J2 queues; sent as a `charts` message at 1 Hz only while the
  drawer is open (`{"type":"charts","on":true}`). The frontend draws what it receives (`frontend/src/ui/charts/`), nothing
  is computed there. The meter is read-only: never let it touch the dynamics.
- **Inspector**: `server/inspector.py` + `ui/InspectorHost.tsx`; frame ids are `vid mod 65536`.
- **Compare** results carry pooled travel-time distributions (`server/compare_dist.py`, `METRICS_VERSION` 3).
- **Validation tab**: `tools/gen_validation.py` -> `data/validation.json` (stale when the engine source changes; a test
  fails, regenerate: about 2 min). Experiments: three built in (`policy_rush`, `flyover_rush`, `surface_closed`).
- If a decision of the user's fails a test: ask before changing it.

