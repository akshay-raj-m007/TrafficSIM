# TrafficSIM: overview for newcomers

TrafficSIM is an agent-based traffic simulator built as a small research workbench. A Python/NumPy engine
simulates vehicles on a hand-built Indian-style (left-hand traffic) road network; a FastAPI server streams it to a
browser, where a Three.js view shows it in true metric 3D with scenario controls, measured KPIs, charts and A/B
comparisons. It was built for the QUEST Lab pre-doctoral application.

## What it simulates

- **Network:** two junctions (J1 signalised, J2 give-way), a flyover with diverge/merge ramps, roads with 1 to 4 lanes
  and a lane drop. Geometry lives only in the backend (`GET /api/network`); the frontend keeps no copy.
- **Vehicles:** several classes (cars, two-wheelers, buses, trucks and so on). IDM car-following plus MOBIL lane changes,
  with a small keep-left bias. Two-wheelers do not filter between lanes.
- **Time:** a fixed step of 0.1 s, never configurable. The clock is an integer tick. Runs are deterministic: same seed
  and scenario give identical trajectories and KPIs.
- **Signals at J1:** `fixed_webster`, `max_pressure`, `max_pressure_threshold`.
- **Live changes:** demand, vehicle mix, J1 policy, flyover open or closed, applied at a tick boundary and logged.

## Setup (about 10 minutes)

Requirements: Python 3.12, Node 22+, optionally Docker. Commands are for Windows (Git Bash); on Linux or macOS use
`.venv/bin/python`.

```bash
# 1. backend
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m uvicorn trafficsim.server.app:app --port 8000

# 2. frontend, in a second terminal
cd frontend
npm ci
npm run dev            # open http://localhost:5173 (proxies /api and /ws to :8000)
```

Or one command, single origin: `docker build -t trafficsim . && docker run --rm -p 8000:8000 trafficsim`, then open
http://localhost:8000. A hosted copy runs on Render's free tier (0.1 CPU, sleeps after 15 min, about a minute to wake,
2 live seats): https://trafficsim-ux3u.onrender.com

### Tests

| What | Command (from) | Time |
|---|---|---|
| Fast backend subset | `.venv/Scripts/python -m pytest -m "not slow"` (backend/) | about 2 min |
| All backend tests | `.venv/Scripts/python -m pytest` (backend/) | about 25 min |
| Lint and format | `.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .` | seconds |
| Frontend | `npm run lint && npm test && npm run build` (frontend/) | under a minute |
| Browser tests | `npx playwright test` (frontend/; set `E2E_PYTHON` to the backend venv python, `PW_CHANNEL=chrome` to use installed Chrome) | about 3 min |

Last full run: 554 backend tests, 91 Vitest tests and 15 Playwright tests, all passing.

## Repository map

| Path | What is there |
|---|---|
| `backend/trafficsim/engine/` | The simulation: vehicles, IDM/MOBIL, signals, gates (spillback guard), live changes, KPIs, charts, run metrics, paired statistics. No web code. |
| `backend/trafficsim/network/` | Road network and lane graph builders. No web code. |
| `backend/trafficsim/server/` | FastAPI adapter: WebSocket sessions, binary frame format, scenario JSON, A/B comparison service, experiments, validation. |
| `backend/trafficsim/data/` | Committed, generated data: free-flow and calibration tables, shipped layout tables (`structures/`), experiments, `validation.json`. |
| `backend/tools/` | Scripts that generate that data and measure things (see below). |
| `backend/tests/` | pytest. `tests/invariants/` holds the five hard invariants. |
| `frontend/src/` | React and Three.js: `scene/` (3D, geometry, interpolation), `api/` (HTTP/WS clients, decoders), `ui/` (panels, charts, inspector). |
| `frontend/e2e/` | Playwright browser tests. |
| `docs/` | This file, `manual_test_plan.md` (52 scenarios), and `project_state_1..10.md` (chronological build log with the reasons for each decision). |
| `Dockerfile`, `render.yaml`, `.github/workflows/` | Single-origin image, Render blueprint, CI and a keep-alive ping. |
| `CLAUDE.md` | The project rules (module boundaries, units, invariants, file length). |

## Architecture in one picture

```
Browser (React + Three.js)  <--WebSocket 10 Hz-->  FastAPI server  --->  Engine (NumPy)
  3D view, controls, charts    JSON + binary frames   one Simulation        IDM + MOBIL, signals,
  decoders, interpolation      per session            per session          detectors, KPIs
        |                                                                       ^
        +---- REST: /api/network, /api/compare, /api/experiments, /api/health --+
```

- Each browser session owns one simulation. Concurrency is capped by `MAX_SESSIONS` (default 2); extra visitors see
  "server busy". Dead connections are freed by a heartbeat, idle ones after 10 minutes.
- Vehicles are streamed as compact binary frames (`12 + 9n` bytes): lane-graph segment, arc length, lateral offset. The
  browser places them on the lane graph and interpolates between simulation states, two frame intervals behind.
- Module boundaries are enforced by `tests/test_boundaries.py`: engine and network never import FastAPI or server code.

## Design rules worth knowing (all tested)

1. **Determinism:** named `SeedSequence` streams, no wall-clock in the engine.
2. **No collisions, no negative speeds,** and never fixed by teleporting.
3. **Spillback guard:** no vehicle enters a junction unless its exit lane has room.
4. **Conservation:** spawned = active + exited; blocked spawns count as unserved demand.
5. **Grade separation:** flyover traffic reaches the surface only via the defined ramps.
6. **Measured, not estimated:** KPIs come from detectors and vehicle positions; delay is actual minus free-flow time.
   Approximations are labelled honestly. Units are metres everywhere; engine axes x east, y north, z up.

## Generated data and when to regenerate

Committed tables carry a digest of every input, and tests fail when they go stale (for example after changing a model
constant, a vehicle class or the lane graph). The failing test names the tool to run, from `backend/`:

| Tool | Regenerates | Time |
|---|---|---|
| `tools/gen_freeflow.py`, `tools/gen_calibration.py` | free-flow and calibration tables | about 80 s and 8 s |
| `tools/gen_structure_tables.py` | 78 shipped lane-count and width layouts (`data/structures/`) | about 55 min on 6 workers |
| `tools/gen_validation.py` | `data/validation.json` (Validation tab) | about 8 min |
| `tools/gen_experiments.py` | the five built-in A/B experiments | about 15 min on 4 cores |
| `tools/gen_golden_frame.py` | frontend decoder fixtures | seconds |

Other tools: `lane_utilisation.py` (every lane carries traffic or is listed with a reason), `load_test.py`,
`measure_stream.py`, `measure_wire.py`, `measure_j2_capacity.py`.

## Using the app

- **Scenario:** presets, demand, vehicle mix, lane counts and widths, J1 signal policy, flyover open or closed. Changes
  to demand, mix, policy and flyover apply live. Changing lanes or widths rebuilds the simulation: shipped layouts take
  about a second even on the hosted server; a layout outside the grid (such as a 3.1 m width) is measured on demand and
  shows a "Preparing this layout" banner with progress.
- **Results drawer:** network fundamental diagram, speed fields per corridor, junction queues, lane-flow overlay.
- **Inspector:** click a vehicle for its state. **Compare tab:** headless A/B runs with paired statistics; built-in
  experiments are precomputed. **Validation tab:** model results against reference values.

## Deployment notes (Render free tier)

Docker runtime from `render.yaml`, auto-deploy on push, health check `/api/health` (also shows session counters). One
uvicorn worker. Environment variables of interest: `MAX_SESSIONS`, `SESSION_HEARTBEAT_TIMEOUT_S`,
`SESSION_IDLE_TIMEOUT_S`, `PREPARE_S_PER_STEP`. A GitHub workflow pings the health endpoint every 5 minutes to keep the
instance awake. Measured numbers (load test, reset times, wire sizes) are in the README's "Deployment" section.

## Known limitations

- The free-flow reference of an unshipped layout builds in the background and can take many minutes at 0.1 CPU.
- The merge-by-green safeguard (`engine/merge_turns.py`) is dormant at J1 by decision; documented in the README.
- Hosted capacity is 2 live sessions; a third sees "server busy".
- Two-wheelers do not filter between lanes. Lane-width speed effects are an approximation, not the HCM adjustment.

## Where to read next

`README.md` (per-topic detail: API, validation, comparison, deployment), then `docs/project_state_*.md` in order for
the history and the reasons behind each decision, and `docs/manual_test_plan.md` for a hands-on check list.
