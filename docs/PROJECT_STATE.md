# TrafficSIM — project state and decision log (handoff for later sessions)

Last updated: Fri 6 Nov 2026, 23:40 IST (step 2b added at the end). **Deadline: Mon 9 Nov 2026, 18:08 IST** (72 h from
start, 18:08 IST Fri 6 Nov). Report the time remaining after every result. Never suggest
/clear; use /compact. Commit after each working step (co-author line in system prompt).
Repo: https://github.com/akshay-raj-m007/TrafficSIM (branch `main`, pushes via plain git;
`gh` is not installed). Local root: `D:\aksha\Projects\TrafficQues`.

## Status
- **Step 1 (baseline): done.** Repo, CLAUDE.md, CI, FastAPI skeleton, static 3D network.
- **Step 2a (vehicles and physics, backend only): done.** 212 tests pass (~4.5 min).
- **Step 2b (vehicles in the 3D view, measured KPIs): done** (see the end of this file).
- **Next: step 3**, not yet specified: scenario controls in the UI, headless A/B runs over
  REST, multi-seed comparison of Webster vs pure vs thresholded max-pressure.
- **Deployment is parked by the user.** No Render or Docker work until the user decides.
  Keep CI green. render.yaml and the Dockerfile already exist; Render free was the chosen
  host (0.1 CPU, 512 MB, 5 GB/month egress, sleeps after 15 min). HF Docker Spaces now
  need PRO, so they are out.

## Locked user decisions
- Python 3.12 + NumPy engine, FastAPI. Each WebSocket session gets its own sim at 10 Hz.
  `MAX_SESSIONS` cap (default 2) returns a "busy" message and close code 1013.
- Vite + React + TS + plain Three.js (not R3F). 1 unit = 1 m, no visual scaling.
- IDM + MOBIL, fixed DT = 0.1 s decoupled from rendering. Seeded RNG everywhere.
- **Left-hand traffic (India).** Lane index 0 = kerb lane (leftmost); higher indices
  toward the median.
- **J1: 4-phase approach-wise split phasing.**
- **Merge:** keep the network. The EB kerb lane `eb_e3:0` is a 450 m acceleration lane
  ending in the 3→2 drop; the merge is gap acceptance there.
- **Car IDM = Treiber & Kesting urban set:** T 1.0 s, a 1.0 m/s², b 1.5 m/s², s0 2 m. The
  user chose this after validation; the old set (a 1.5 / T 1.2 / b 2.0) was string-stable.
- Rules: no magic numbers (every parameter named, with unit and source); KPIs measured
  not estimated; label approximations honestly; source files ≤ ~200 code lines; engine
  and network import only stdlib + numpy (AST test); plan first, explain before changing
  any user decision; show actual numbers, not just pass/fail.

## Hard invariants (tests in backend/tests/invariants)
1. Determinism: per-step sha256 of the state, identical for the same seed.
2. No collision: per-segment body gaps > 0 (tails included), no conflict-point overlap
   in junctions, v ≥ 0 (harness.py, independent of the engine).
3. Spillback. Precise definition: at commitment, the guaranteed exit-lane room (rear of
   the last vehicle + v²/2b of that vehicle, minus the length + s0 of vehicles entering
   first) is ≥ own length + s0. Outcome check: 0 vehicle-seconds held in junction boxes.
4. Conservation: generated = active + exited + queued every step; queued = unserved.
5. Grade separation: network topology + 5.5 m clearance + vehicle-level transitions only
   via ramps.

## Demo network (backend/trafficsim/network/demo*.py)
x east, y north, z up. EB corridor runs on the north side.
- **Roads:**
  - `eb_w4` 4 lanes (x −1000 → −450). Diverge: lanes 0,1 → `eb_surf_w` (2 lanes, to J1);
    lanes 2,3 → `eb_ramp_up` → `eb_flyover` (deck z 6.5, x −270 → 270) → `eb_ramp_dn`.
  - Merge at +450: `eb_surf_e` (1 lane, 3.0 m) + ramp → `eb_e3` (3 lanes). Lane 0 is
    dropped at x 900 → `eb_e2` (2 lanes) → J2 (x 1100) → `eb_out`.
  - WB mirror: `wb_in` → J2 → `wb_e2` → widening at 900 → `wb_e3` (3) → diverge (lane 0
    → `wb_surf_e` 1 lane to J1; lanes 1,2 → `wb_ramp_up`/`wb_flyover`/`wb_ramp_dn`) →
    merge → `wb_w4` (4).
  - Cross street at J1: `n1_in`/`n1_out`/`s1_in`/`s1_out` (2+2 lanes, 3.25 m).
  - J2 minor road: `n2_in`/`n2_out` (1+1, 2.75 m, give-way).
- **Zones:** W, E, N1, S1, N2. Lane widths 2.75 / 3.0 / 3.25 / 3.5 m.
- **J1 movements:** W lane 0 left only; lane 1 through + right.
- **Gotcha:** W→E fastest routes use the flyover, so the surface through movements at
  J1 carry no OD demand (calibration uses explicit two-road routes for them).
- 24 roads, 50 lanes, 48 connectors (22 junction turns), 72 engine segments. Shortest
  connector 13.1 m ≥ 12 m truck (single-tail scheme relies on this; asserted).

## Engine architecture (backend/trafficsim/engine)
- `constants.py`: DT 0.1. Integer tick; t = tick/10.
- `rng.py`: named SeedSequence streams spawn / vehicle_class / route / behaviour.
  Append-only; first values are pinned in a test.
- `vehicle.py`: class table and SoA `VehicleState` (fields vid, cls, seg, s (front),
  v, acc (realised), route, rpos, nxt, tail, off, goodbits, lc_timer, t_gen, t_ins).
  Power-to-mass: car 48, truck 6, two-wheeler 33, CAV 48 W/kg.
- `params/driving.py`, `params/control.py`: all named parameters with sources (IDM,
  MOBIL, lane width, HCM gaps, ITE, Webster bounds, standoff, calibration).
- `lanegraph.py`: segments = lanes + junction connectors. Turn speed limit
  sqrt(3.0·R_min). v0_eff table (lane-width factor on lanes only). nbr, pred,
  ends_at_junction.
- `routes.py`: fastest road route per OD. `good` lanes per rpos. `next_seg`
  (NEXT_NONE −1, NEXT_EXIT −2). `add_explicit`. `refresh_lane_cache` (off/goodbits).
- `demand.py`: Poisson per zone, FIFO queues, insertion requires gap ≥ s0 + v·T.
  `place()` is for scripted vehicles.
- `leaders.py`: occupancy sorted by (seg, s) incl. ghost tails and incidents (static,
  row −1). `find_leaders`, `walk_ahead` (front vehicles only), `stop_gaps` (own lane
  end / closed gate for every approaching vehicle; obstacle at line + s0 − 1 m standoff).
- `dynamics.py`: acc = min(IDM leader, IDM stop point, power/grade limit,
  anticipation ≥ −b).
- `idm.py`: x⁴ written as x*x*x*x. Ballistic update.
- `mobil.py` + `lc_neighbours.py` + `lc_sync.py`: discretionary MOBIL re-evaluated
  every 1 s, staggered. Mandatory changes every step, with b_safe 4 → 6 within 200 m.
  Pairwise-safe concurrent changes. No lane changes within the stopping distance of a
  stop line. Synchronisation: the rear vehicle drops back at ≤ b. Lane-change event log.
- `gates.py`: per-step candidates nearest-first.
  - Permission requires: signal; room ≥ need; conflicting connectors not reserved and
    bodies past the conflict point; J2 yielding movements with arrival at the conflict
    point ≥ t_c (HCM four-lane values 6.9 / 7.5 / 4.1 s).
  - Commitment (reservation) when d ≤ v²/2b + v·DT + ½a·DT² + 1 m. Reservations are
    never revoked; crossing a closed line raises EngineInvariantError.
  - Logs accepted_gaps, commit_room and room_seen.
- `transfer.py`: segment transfers, exits, ExitRecord, JunctionEntry (room at commit
  and at entry), LaneChangeEvent.
- `signals.py` + `webster.py` + `calibration.py`:
  - Amber 2.82 s and all-red 3.10 s (E-W) / 4.00 s (N-S) from ITE formulas.
  - Saturation flow measured per movement by releasing a standing queue of 24 vehicles,
    skipping 4, lane changes off. Cached per (net id, mix, junction); about 8 s per mix.
  - Webster with C_MAX 120 s, G_MIN 7 s, greens ∝ y with G_MIN inside the cycle.
  - MaxPressure (Varaiya, weighted by saturation flow; G_MIN 7, G_MAX 60).
  - Scenario `signal_control` is `fixed_webster` | `max_pressure` | `uncontrolled`.
- `loop.py` phase order: signals → demand → occupancy + gates → leaders → lane changes
  (re-run occupancy/gates/leaders if any) → stop points/dynamics → ballistic update →
  transfer → box-held metric.
  - Counters: emergency_brakings (realised decel > 9), lane_changes,
    box_stopped_vehicle_s.
  - Empty-network fast path; `allow_lane_changes` flag; `place_vehicle`; `row_of`.
- `scenario.py`: Scenario(seed, duration_s, demand OdFlow, vehicle_mix, signal_control,
  incidents). `presets.py`: DEMO_DEMAND, `scaled()`.
- `network/conflicts.py`: merge/cross conflicts with the conflict-point arc length on
  both paths.

## Server / frontend (unchanged in 2a except pacing)
- `server/pacing.py`: StepPacer with an exact Fraction, so k× = k sim-s per wall-s at
  any tick_hz.
- WS protocol:
  - `hello`, then `tick {tick, t, speed, done, step_ms, lag_ms}`.
  - Client messages: `set_speed` (0/1/2/5/10), `reset{seed}`, `ping`.
  - The server currently starts `Simulation(network, Scenario(seed))` with no demand,
    so no vehicles are streamed yet.
- Frontend: dark 3-column layout and static 3D network from /api/network (coords.ts is
  the only axis mapping (x, z, −y)). Camera presets; telemetry shows measured link stats
  only; KPI and scenario panels are step-2 placeholders.

## Measured results to remember
- **Performance:** 1.7–2.3 ms/step at ~200 vehicles, 4.3 ms at ~630 (about 2% of one
  core at 1×, 17–23% at 10×).
- **Ring:** stable ≤ 45 veh/km; stop-and-go from 70 veh/km; waves −14.4 km/h.
  Fundamental-diagram max 2,074 veh/h at 55 veh/km.
- **Saturation:** cars 1,625–1,644, mixed 1,602–1,668; turns 1,093–1,208 veh/h.
- **Webster (demo + N-S 300/300):** Y 0.649, L 25.5 s, C0 123.1 s → C 120 s, greens
  30.3/36.9/13.6/13.6 s.
- **Max-pressure** switches too often (mean green ~8 s; 620 vs 640 served). The user was
  told; a switching threshold is not added (user's call).
- **J2 minor road** capacity below HCM at high conflicting flow (156 vs 287 veh/h)
  because platooned major traffic has about 4× fewer usable gaps.
- **Truck on the up-ramp:** 93% of desired speed at free flow; 36.7 vs 45.9 km/h from a
  standing start.

## Commands
```bash
cd backend && .venv/Scripts/python -m pytest -q        # ~4.5 min; add -s to see printed numbers
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m uvicorn trafficsim.server.app:app --port 8000
cd frontend && npm run lint && npm test && npm run build
```
Windows notes:
- Avoid non-ASCII characters in test prints (cp1252 console).
- Use scratchpad patch scripts instead of complex inline heredocs.
- Headless browser screenshots: playwright-core + local Chrome (script in the session
  scratchpad).

## Step 2b (done 6 Nov 2026 evening)
- **Workflow rule from the user:** push after work is built and tested; rebuild the frontend
  and restart localhost so the user can analyse it. Deployment still parked.
- **Part A:** `slow` pytest marker (strict markers); fast subset `pytest -m "not slow"`
  (~40 s, 243 tests), full suite ~7 min (CI). README has ring-road waves (−14.4 km/h), the J2
  platoon finding (156 vs HCM 287 veh/h), and the corrected discharge explanation: the 1,644
  veh/h stop-line flow is NOT a capacity drop; steady maximum at J1's 39 km/h desired speed is
  1,766 (start-up transient −7 %), the rest of the gap to HCM is the 40 km/h desired-speed
  ceiling. Measured start-up loss at J1 is 3.8–5.5 s (HCM default l1 = 2 s used in Webster).
- **Part B:** `max_pressure_threshold` (G_MIN 15 s, threshold derived = lost time per switch
  10.9 s ≈ 4.1 veh forfeited, in pressure units 5,498). Pre-registered, not tuned.
- **Part C (engine/):** `pose.py`, `detectors.py` (12 detector lines, 60 s window),
  `queues.py` (chain gap ≤ 7.0 m derived), `freeflow.py` (+ committed table, 80 values),
  `kpi.py` (`Simulation.kpi_snapshot()`), `presets.DEMO_KPI_LAYOUT`. Delay = (t_exit − t_ins)
  − free-flow(route, class); entry-queue wait reported separately. A lone vehicle has delay 0
  exactly (test).
- **Part D (server/):** `frames.py` (binary frame), `session_config.py` (query params
  seed/signal/demand_scale), `stats.py`, `protocol.py`, `ws.py`. Frames only when the sim
  advanced. Calibration table committed (`data/calibration_demo.json`).
- **Part E (frontend/):** `api/frame.ts`, `scene/interpolator.ts` (tick-domain clock, delay
  2 frame intervals, 250 ms hiccup cap), `scene/vehicles.ts` (InstancedMesh per class + lamp
  mesh), `scene/instanceMatrix.ts`, `scene/speedColor.ts`, `ui/KpiPanel.tsx`, `ui/Legend.tsx`.
  48 Vitest tests. Debug hook `window.__trafficDebug.probe(n)` returns render tick + car poses.
- **Measured:** frame 12 + 13 n bytes; on the wire (permessage-deflate negotiated) 736 B/frame
  at 178 vehicles (7.4 KB/s, 187 h per 5 GB) and 4,564 B at 676 vehicles (46 KB/s, 30 h per
  5 GB); uncompressed 2,540 / 8,982 B. Wire compression is only ~2x (no shared context between
  frames); offline what-if (not implemented): delta frames 1,640 B vs 2,687 B per frame alone
  at ~370 vehicles. Step cost 1.8 ms (160 veh) / 4.3 ms (640 veh); encode 0.3–0.8 ms.
- **Smoothness (headless Chrome, software GL ~27 fps):** no stalls; median frame-to-frame change
  of apparent speed vs render tick 0.01–0.02 %, p95 1.7–3.5 %. Real 60 fps not measurable here.
- **Known visual limits:** plain boxes (no wheels/windows); chord cutting at 5–10×; lane
  changes are instantaneous in the model (3 s display blend only); vehicles in a blend can
  overlap neighbours slightly.
- **Pitfall:** uvicorn on Windows: stop old servers with the task tool (killing by PID is
  blocked). Default demo demand overloads the J2 minor road (queue grows) — a legit result of
  the J2 finding, not a bug.

