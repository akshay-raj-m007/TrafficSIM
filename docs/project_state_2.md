# TrafficSIM — project state 2: step 2b (vehicles visible, KPIs measured)

Companion to [PROJECT_STATE.md](PROJECT_STATE.md), which covers everything up to step 2a
(engine, junctions, signals, invariants, validation). This file covers **step 2b only**.
Read PROJECT_STATE.md first, then this one.

Written: Fri 6 Nov 2026, 23:30 IST. **Deadline: Mon 9 Nov 2026, 18:08 IST.** Time left at
writing: about 66 h 30 min. Report the time remaining after every result; never suggest
/clear (use /compact).

## Status and workflow rules
- **Step 1, 2a, 2b done.** Everything is committed and pushed to
  https://github.com/akshay-raj-m007/TrafficSIM (`main`). Localhost runs the final code at
  http://localhost:8000 (uvicorn on the final commit, frontend built).
- **Next: step 3**, not yet specified. Expected: scenario controls in the UI, headless A/B runs
  over REST, and the multi-seed comparison of Webster vs pure max-pressure vs thresholded
  max-pressure (to be reported as a result, not tuned).
- **Deployment is parked** by the user (no Render or Docker work). CI must stay green.
- **Push rule (new in 2b):** after a part is built and tested, commit and push, then rebuild the
  frontend (`npm run build` in `frontend/`) and restart uvicorn so localhost shows it. Stop the
  old server with the task tool (killing by PID is blocked in this environment).
- Standing rules unchanged: parameters are named constants with units and sources; KPIs are
  measured, never estimated; approximations are labelled honestly; source files under ~200
  lines; plan first and say which parts are riskiest; show actual numbers.
- Commit trailer from now on: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
  (the model was switched to Sonnet 5.5 at the start of 2b).

## The user's decisions at the start of 2b (all done)
1. **Max-pressure:** keep the textbook version unchanged and add a second, selectable variant
   with a switching threshold and a longer minimum green. Compare Webster vs pure vs thresholded
   with several seeds later; do not tune one version until it looks good.
2. **Stop-line discharge (~1,630 veh/h):** do not tune to hit 1,900; explain properly. The user
   doubted calling it a "capacity drop". Outcome: the doubt was right (see below).
3. **Slow tests:** mark long runs `slow` so a fast subset can run after every change; CI runs all.
4. **README:** add the ring-road wave speed and the J2 platoon finding.
5. **2b scope:** render vehicles (InstancedMesh per class, true metres, speed colour, brake
   lights, real elevation and pitch), smooth interpolation incl. 0.25x, compact WebSocket
   frames with measured size/bandwidth at ~200 and ~600 vehicles, backend-computed measured
   KPIs, legend, header with clock and agent count. No scenario controls beyond speed and
   pause/reset (that is step 3).

## Findings that change earlier statements
- **The J1 discharge is NOT a "capacity drop".** My earlier comparison mixed desired speeds
  (ring road at 59 km/h vs J1 at 39 km/h). Same-speed numbers, cars only: steady maximum on a
  ring at 39 km/h = 1,766 veh/h; J1 queue discharge = 1,644 (start-up transient, −7 %); at a
  59 km/h desired speed the ring maximum is 2,074 and discharge 1,772; with a = 1.5 m/s² as well,
  1,977. So: a desired-speed ceiling (40 km/h urban limit) plus an acceleration-limited start-up.
  HCM's 1,900 needs both a higher desired speed and a ≈ 1.5 m/s², i.e. a different parameter
  set. Corrected in the README ("Known differences from HCM") and the test docstring.
- **Measured start-up lost time at J1: 3.8–5.5 s per movement (mean 4.5 s)**, about twice the HCM
  default l1 = 2 s that the Webster lost-time sum uses. Not changed; offered to the user.
- **My bandwidth model was wrong.** A zlib stream with shared context predicted ~1,400 B/frame at
  676 vehicles; on the real wire it is 4,564 B (see "Measured numbers").
- **J2 platoon finding** is a hypothesis about the source of bunching (lane drop / flyover merge /
  signal) that has not been isolated; the README says so.

## Part A: housekeeping
- `slow` marker registered in `backend/pyproject.toml` with `--strict-markers`. 27 tests over
  ~5 s are marked (invariant/validation runs, J2 capacity, spillback, signal timing, lane-change
  fixtures, some pacing cases, encoder/blend runs). Fast subset `pytest -m "not slow"` = 243
  tests in ~40 s; full suite 282 tests in ~7 min (what CI runs).
- `tests/test_fast_subset.py` fails if the fast subset loses a whole test area;
  `tests/validation/test_ring_smoke.py` gives the validation area quick tests.
- The end-to-end pacing test tolerance is ±7 % over a 3 s window (the resolution of 100 ms frames).
- README additions: ring road (stable ≤ 45 veh/km; stop-and-go from 70; waves −14.4 km/h, method:
  space-time cross-correlation), J2 platoon finding (156 vs HCM 287 veh/h; headway CV 1.42; 40 vs
  161 usable gaps per hour), discharge explanation table, signal controllers.

## Part B: `max_pressure_threshold` (pre-registered, not tuned)
- `Scenario.signal_control` is now one of `fixed_webster`, `max_pressure` (textbook, unchanged),
  `max_pressure_threshold`, `uncontrolled` (calibration/experiments only).
- Parameters fixed before any comparison: minimum green `G_MIN_THRESHOLD_S = 15 s` (FHWA Signal
  Timing Manual range 5–15 s); switching threshold **derived**: switch only if the best
  alternative phase beats the current one by the capacity a switch forfeits. Lost time per switch =
  mean intergreen + mean measured start-up loss = 10.9 s at J1; forfeited = lost × s_ref / 3600 =
  4.08 veh (s_ref = mean measured saturation flow 1,346 veh/h); threshold in pressure units
  (vehicles × veh/h) = 5,498. G_MAX 60 s and the forced switch are unchanged.
- `engine/calibration.py` now also measures start-up lost time (HCM definition: time the 4th
  vehicle crosses minus 4 saturation headways). Classes: `MaxPressure(g_min_s, threshold)`,
  `MaxPressureThreshold`; every controller has a `.name`.
- One-seed orientation run (seed 4, 600 s, demo demand + N-S 300/300): greens 20 / 40 / 23, served
  375 / 366 / 381 (Webster / pure / thresholded). Not a ranking.
- Tests: `tests/engine/test_signals_threshold.py` (hysteresis and minimum green with synthetic
  pressures, pure rule unchanged, derivation, three controllers safe and never conflicting).

## Part C: engine measurement layer (`backend/trafficsim/engine/`, pure Python)
- `pose.py` — `PoseTable`: world pose of each vehicle's centre (front − L/2; vehicles straddling
  segments use the `tail`) on real lane/connector polylines; x, y, z, heading, pitch. One
  `searchsorted` for all vehicles. Tests: no jumps along a whole route (max 1.36 m/step), deck
  z = 6.500 m, peak ramp pitch 3.10° = analytic 5.4 % smoothstep grade.
- `detectors.py` — front-bumper crossings over all lanes of a road, 60 s window → veh/h (one
  vehicle = 60 veh/h); detectors ≥ 20 m from road ends (asserted). 12 detectors in
  `presets.DEMO_KPI_LAYOUT`: W_IN, E_IN, FLY_EB, FLY_WB, DROP_3, J1 W/E/N/S approaches, J2
  W/E/N approaches.
- `queues.py` — unbroken chain of vehicles slower than 2.2 m/s from the stop line; each within
  `QUEUE_MAX_GAP_M = s0_max + V_QUEUED·T_max = 7.0 m` (derived, not fitted). Length = line to rear
  of the last queued vehicle (longest lane); count summed over lanes. 7 approaches.
- `freeflow.py` — free-flow time per (route, class) **measured by the engine** (one vehicle alone,
  signals off, `Demand.insert_now`). A cold computation takes ~70–80 s, so values live in a
  committed table `trafficsim/data/freeflow_demo.json` (80 values) with an input digest
  (`input_digest`); regenerate with `python tools/gen_freeflow.py`. A stale table is ignored and
  the values are measured in a background thread.
- `kpi.py` — `KpiHub`, `KpiLayout`, `KPI_DEFS` (definition strings). `Simulation(network,
  scenario, kpi_layout=None)` and `Simulation.kpi_snapshot()` return a plain dict: counts, J1
  signal, flow, queues (+60 s max), delay, unserved. **Delay** = (t_exit − t_ins) −
  free-flow(route, class), cumulative and last 5 min, entry-queue wait (t_ins − t_gen) separate,
  no clipping of negative values. Unserved = entry queues and oldest wait.
- `LaneChangeEvent` gained `s_from` and `s_to`; `Demand.insert_now`, `Demand.class_indices`.
- New constants in `params/control.py`: `DETECTOR_WINDOW_S`, `DETECTOR_MIN_END_CLEARANCE_M`,
  `KPI_RECENT_WINDOW_S`, `QUEUE_SAMPLE_PERIOD_S`, `G_MIN_THRESHOLD_S`.
- Tests (`tests/test_pose.py`, `tests/test_kpi.py`) recompute everything independently: detector
  totals/windows vs brute-force crossings, queue by hand and edge cases, lone-vehicle delay = 0,
  mean delay vs manual recomputation, JSON snapshot, conservation, determinism, table freshness.

## Part D: server streaming (`backend/trafficsim/server/`)
- `frames.py` — binary vehicle frame, little-endian struct-of-arrays, **12 + 13 n bytes**:
  header (u8 type=1, u8 J1 phase, u8 J1 state, u8 epoch, u32 tick, u16 n, u8 speed index, u8 pad),
  then columns u16 id (vid & 0xFFFF), u16 x, u16 y, u16 z, u16 heading, i8 pitch, u8 speed, u8
  flags (bit0 brake, bits1–2 class). Steps: position 0.05 m, z 0.01 m (origin −1 m), heading
  2π/65536, pitch 0.001 rad, speed 0.1 m/s; offsets and steps go to the client in `hello`.
  Brake flag = realised deceleration ≥ 0.5 m/s², or standing (v < 0.1 and acc < 0.1).
  `pack_frame`, `unpack_frame`, `FrameEncoder`, `format_for`.
- **Lane-change blend:** the model changes lanes instantly; the encoder blends the lateral offset
  over `LC_BLEND_S = LC_COOLDOWN_S = 3 s` (smoothstep) for display only (render-only state).
- `ws.py` — `LiveSession`: frames only when the simulation advanced (0.25x = one frame per 400
  ms); `kpi` and `stats` JSON once per wall second; reset bumps the epoch and re-sends `hello`;
  malformed client messages return a JSON-safe error (earlier a validator exception killed the
  session).
- `protocol.py` — speeds `0, 0.25, 0.5, 1, 2, 5, 10`; `hello` carries class dimensions (length,
  width, **height_m** — new visual-only field in `VehicleClass`: 1.5 / 3.2 / 1.5 / 1.5 m), frame
  format, `kpi_defs`, epoch, seed, signal, demand scale. Binary frames carry the speed index.
- `session_config.py` — `SessionParams(seed, signal, demand_scale)`; live session default = demo
  demand, `fixed_webster`, seed 42, 3600 s. WebSocket query parameters `seed`, `signal`,
  `demand_scale` (0.25–3) are an **experiment seam, no UI yet**; invalid values close with 1008.
- `stats.py` (`StreamStats`), `config.py` (`warm_up`), `app.py` (lifespan warm-up; unhandled
  `WebSocketDisconnect` in cleanup fixed).
- **Calibration table:** `trafficsim/data/calibration_demo.json` (saturation flow and start-up
  loss per J1 movement for the default mix, digest = free-flow digest + mix), generated by
  `python tools/gen_calibration.py` (~8 s). Sessions and tests start instantly instead of
  spending ~8 s; tests fail when stale and re-measure to prove equality.
- Tools in `backend/tools/`: `gen_freeflow.py`, `gen_calibration.py`, `gen_golden_frame.py`,
  `measure_stream.py` (frame size/CPU, zlib simulation), `measure_wire.py` (real server, TCP
  byte-counting proxy, two identical sessions with/without permessage-deflate).
- Tests: `tests/test_frames.py` (round trip max 2.49 cm, golden fixtures current, brake convention,
  lane-change blend, format), `tests/test_server.py` (rewritten for binary frames), `tests/ws_util.py`,
  `tests/test_pacing.py` (sim time read from frame headers), `tests/test_stream_budget.py`,
  `tests/test_calibration_table.py`.

## Part E: frontend (`frontend/src/`)
- `api/frame.ts` decodes frames over typed arrays; `api/types.ts` / `api/protocol.ts` /
  `api/simSocket.ts` updated (binary vs JSON messages, `onFrame`, `onKpi`, `onStats`). Golden
  fixtures `api/fixtures/golden_frame.{bin,json}` are written by the Python encoder and decoded
  identically in Vitest (`*.bin` is marked binary in `.gitattributes`).
- `scene/interpolator.ts` — pure `FrameInterpolator`: render clock in **simulation ticks**,
  advances at `speed × 10 ticks/s`, held `INTERP_DELAY_FRAMES = 2` frame intervals behind the
  newest frame, wall-clock hiccup cap 250 ms, linear interpolation by vehicle id, shortest-angle
  heading, vehicles that vanish are held until the pair advances, epoch change/backward tick
  clears the buffer, paused sessions settle on the last tick. Known limit: at 5–10× consecutive
  frames are 0.5–1 s of sim time apart, so junction turns are interpolated along chords.
- `scene/instanceMatrix.ts` — right-handed basis (forward, up, right) from heading and pitch,
  through the single axis conversion (x, z, −y); `scene/speedColor.ts` — fixed 0–60 km/h ramp
  (red → amber → cyan); `scene/vehicles.ts` — one `InstancedMesh` per class (true length × width ×
  height from `hello`, capacity 2,500 each) plus one lamp mesh with instances only for braking
  vehicles; `scene/sceneManager.ts` — pushes frames, samples the interpolator each display frame;
  debug hook `window.__trafficDebug.probe(n)` returns `{tick, cars:[{id,x,y,z}]}`.
- UI: `ui/Header.tsx` (sim clock from the frame tick, agent count, speeds incl. 0.25× and 0.5×,
  pause, reset, status), `ui/KpiPanel.tsx` (J1 phase and timer, flows, queues, delay, unserved,
  hover definitions), `ui/TelemetryPanel.tsx` (KPIs + measured stream block), `ui/Legend.tsx`
  (speed ramp, brake light, class sizes, turn guides); `App.tsx` rewritten; CSS additions.
- Vitest: 48 tests (decoder + golden, interpolator at 0.25/0.5/1/2/10×, pause, reset, late frame,
  appear/vanish, heading wrap, matrices with true dimensions and pitch, colour ramp, protocol).

## Measured numbers (2b)
- **Frame size:** exactly 12 + 13 n bytes.
- **On the wire** (`measure_wire.py`, real uvicorn, TCP proxy, 10 Hz, includes KPI/stats ≈ 2.3
  KB/s; two clients with identical parameters):

  | vehicles | speed | compression | B/frame | KB/s | MB per hour | h per 5 GB |
  |---|---|---|---|---|---|---|
  | 178 | 1× | none | 2,540 | 25.5 | 92 | 54 |
  | 178 | 1× | deflate | 736 | 7.4 | 27 | 187 |
  | 676 | 1× | none | 8,982 | 90.3 | 325 | 15 |
  | 676 | 1× | deflate | 4,564 | 46.0 | 165 | 30 |
  | 172 | 10× | none / deflate | 2,477 / 858 | 24.8 / 8.6 | 89 / 31 | 56 / 161 |
  | 632 | 10× | none / deflate | 8,442 / 4,375 | 81.1 / 41.5 | 292 / 150 | 17 / 33 |

  Wire compression is only ~2× because the real server/client pair compresses each frame alone
  (matches offline "each frame compressed alone" at ~370 vehicles: 4,818 raw → 2,687 B; with
  shared context 1,147 B; delta-coded frames 1,640 B alone / 455 B with shared context — **not
  implemented**, options for a hosting decision: delta frames, lower frame rate with client
  extrapolation, or simulating in the browser).
- **CPU on the dev machine:** simulation step 1.8 ms at ~160 vehicles, 4.3 ms at ~640 (about 2 % of
  one core at 1×, 17–23 % at 10×); frame encode 0.3–0.8 ms; KPI snapshot 0.6–2.6 ms (once/s).
  Free-flow table cold computation 68–81 s; calibration table 6–8 s.
- **Smoothness** (headless Chrome, software rendering, ~27 fps, 1100×520): no stalls at 0.25×,
  1×, 10×; median frame-to-frame change of apparent speed against the render tick 0.01–0.02 %, p95
  1.7–3.5 %, p99 ≤ 5 % at 0.25×/1×, ~10 % at 10× (real acceleration + chords). **Real 60 fps
  could not be measured here**; a first attempt using wall-clock timestamps was contaminated by
  callback-order jitter and was discarded.
- **Demo KPIs at ~210 s of sim time:** ~177 agents, mean delay ~17 s (n ≈ 40), flows 120–1,900
  veh/h by detector. Over 15 min the J2 minor road queue grows to 33 vehicles / 231 m because the
  default minor-road demand (200 veh/h) exceeds its measured capacity.
- **CI** (Linux, Docker build included) passed on the Part C/D/E push; the committed table digests
  are therefore platform-stable.

## Known visual and modelling limits (reported to the user)
Plain box vehicles (no wheels/windows; two-wheelers tiny); chord cutting at 5–10×; instantaneous
lane changes in the model with a display-only 3 s blend (vehicles mid-blend can slightly overlap a
neighbour); brake lamps hard to see at overview distance; speed-colour ramp not colour-blind
tested; the browser smoothness at real 60 fps is unverified.

## Open items / ideas not done
- Use the measured start-up loss (≈ 4.5 s) instead of HCM l1 = 2 s in the Webster lost-time sum
  (offered, not decided).
- Delta-coded frames / shared compression context if bandwidth matters for hosting.
- Isolate what causes the J2 major-stream bunching.
- Step 3: scenario controls (seed, signal control, demand scale, mix, incidents), headless A/B REST
  endpoint (process pool), multi-seed controller comparison, load test for the session cap.
- Deployment decision (Render free = 0.1 CPU, 512 MB, 5 GB/month egress, sleeps after 15 min).

## Addendum (7 Nov 2026): J2 minor approach flared into a left lane and a right lane
- **Trigger:** the user noticed the J2 minor road filling up and asked whether that was a mistake.
  Diagnosis (instrumented lead vehicle, HCM comparison from the simulated flows): not a code
  bug, but the single shared minor lane let a waiting right-turner (crossing both EB lanes and
  merging into WB lane 1, 7.5 s gap in ~1,230 veh/h) block left-turners whose gap was open 37 %
  of the time. Served 48 veh/h vs 216 from HCM's shared-lane formula for the same flows. The
  right turn had never been validated against HCM (only the left), so the earlier "platoons"
  explanation covered only part of the gap.
- **Decision (user chose it from four options):** separate left/right lanes. Rejected: lowering
  demand only, a waiting-time-dependent critical gap (unsourced parameters), leaving as is.
- **Change:** `build_demo_network(minor_approach_lanes=2)` (default); `1` reproduces the original
  network exactly. N2 approach `n2_in` has 2 lanes of 2.75 m: lane 0 (kerb) left turn
  `n2_in:0>eb_out:0`, lane 1 right turn `n2_in:1>wb_e2:1`. `J2_MINOR_SETBACK_M = 3.0`: the
  approach stop line is 3 m further north because the kerb-lane left-turn path would otherwise be
  ~10 m, shorter than the 12 m truck (the engine rejects segments shorter than the longest
  vehicle). Only the entry side moved; every other connector is bit-identical to the old
  network (test). Junction plate extended to the set-back.
- **Regenerated** `freeflow_demo.json` (only N2-origin routes changed) and `calibration_demo.json`
  (only its digest changed: J1 saturation flows are untouched).
- **Proof nothing else changed:** `tests/engine/test_j2_minor_lanes.py`: with no N2-origin
  demand, exits, lane changes and junction entries are identical on both networks (uncontrolled
  and Webster); minor turns share no conflict; right turn still crosses both EB lanes.
- **Measured:** left turns served in 600 s with a saturated right turn: 23 (27 left-only) vs 8
  on the old lane; right turn vs HCM: 980 veh/h conflicting → HCM 207, simulation 132 veh/h
  (64 %), min accepted gap 7.51 s ≥ 7.5 s; default demo 900 s: 17 N2-origin trips completed (7
  before), N2 queue peak 142 m (238 m), right-turn lane still queues (18 standing) because its
  100 veh/h demand exceeds the crossing capacity (a scenario input, left as is).
- **Docs:** the user renamed `PROJECT_STATE.md` to `project_state_1.md` (untracked/uncommitted
  rename at the time of this change).

## Commands
```bash
cd backend && .venv/Scripts/python -m pytest -m "not slow"   # fast subset, ~40 s
cd backend && .venv/Scripts/python -m pytest                 # everything, ~7 min (CI)
cd backend && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .
cd backend && .venv/Scripts/python tools/gen_freeflow.py     # when the lane graph / classes / constants change
cd backend && .venv/Scripts/python tools/gen_calibration.py  # same trigger (~8 s)
cd backend && .venv/Scripts/python tools/gen_golden_frame.py # only if the frame format changes
cd backend && .venv/Scripts/python tools/measure_stream.py   # frame size / CPU
cd backend && .venv/Scripts/python tools/measure_wire.py     # real bytes on the wire (~5 min)
cd frontend && npm run lint && npm test && npm run build
cd backend && .venv/Scripts/python -m uvicorn trafficsim.server.app:app --port 8000 --workers 1
```
Environment notes: Windows; avoid non-ASCII in test prints (cp1252); prefer scratchpad patch
scripts over long inline heredocs; the headless-Chrome scripts (playwright-core + local Chrome)
live in the session scratchpad, not in the repo.
