# TrafficSIM — manual test plan

Written Sun 8 Nov 2026, before submission (deadline Mon 9 Nov 2026, 18:08 IST). Context: `README.md` and
`docs/project_state_1.md` … `project_state_9.md`. 72 scenarios (most important first inside each area; the quick pass is the P1 rows only).

**Where:** *Live* = https://trafficsim-ux3u.onrender.com/ (free Render instance, 2 live seats). *Local* =
`http://localhost:8000` (backend `uvicorn trafficsim.server.app:app --port 8000` from `backend/` with `frontend/dist`
built, or `npm run dev` on :5173). *Both* = run on each.
**Priority:** P1 must work for submission, P2 should, P3 nice.
**Result column:** write `pass` / `fail` and a note. "Relates to" names the finding, fix or invariant (so past bugs stay fixed):
`PS5` = project_state_5 etc.; *INV-n* = the hard invariants of `CLAUDE.md`: 1 determinism, 2 no collision / no negative speed,
3 spillback guard, 4 conservation (spawned = active + exited), 5 grade separation.

Tips: keep the browser console open (F12): **any console error is a fail** of the scenario in which it appears. Use 5× or
2× speed to save time; on the live site avoid 10× (see L4). The default seed is 42.

---

## A. First visit and wake-up

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| A1 | First load, healthy server | Open the live URL in a fresh tab. | Page and 3D scene appear within a few seconds; header shows **live**; vehicles appear within ~20 s at 1×; no banner, no console error. | PS9 deployment; waking-up banner must not show when healthy | Both | P1 | |
| A2 | Health and shipped data | Open `/api/health`, `/api/validation`, `/api/experiments`. | Health: `status ok`, `sessions_max 2`, `heartbeat_timeout_s 30`, `idle_timeout_s 600`. Validation JSON present, `stale:false`. Five experiments, all `available:true`, `stale:false`. | PS6/PS7 stale-digest policy; hosted env vars | Both | P1 | |
| A3 | Waking-up message | (Live) After the site has been idle, or by blocking the websocket in dev tools, reload. | If the page loads but the socket is not up in ~4 s, a banner "Waking up the server … about a minute" shows and the page connects by itself. | PS9 wake-up banner (`waking.spec`) | Both | P2 | |
| A4 | Site still reachable after 15+ min idle | Leave the live site alone for 20 minutes, then open it. | Loads normally (the keep-alive pings every 5 min). If it hangs: dashboard → Manual Deploy → Deploy latest commit; note it here. | Free instance did not wake after sleep; `keepalive.yml` | Live | P1 | |
| A5 | Actions keep-alive runs | GitHub → Actions → `keepalive`. | Recent runs every ~5 min, green (some may be late). | `keepalive.yml` | Live | P2 | |
| A6 | Local start from scratch | `cd backend && .venv/Scripts/python -m uvicorn trafficsim.server.app:app --port 8000`; open :8000. | Starts in under a minute (first session builds J1 tables from the committed files, not measured); page works. | PS5 F1/F3 tables and digest | Local | P2 | |

## B. Camera and the 3D view

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| B1 | View buttons | Click **overview, J1, flyover, lane drop, J2**. | Camera jumps to each; J1 shows the signalised box with the deck over it; "lane drop" shows the section east of the merge; labels readable. | PS2 camera presets | Both | P1 | |
| B2 | Orbit, zoom, pan; drag is not a click | Drag, wheel, right-drag on the scene. | Smooth; camera stays above ground; **dragging never opens the inspector**. | PS9 picking (drag ≠ click) | Both | P2 | |
| B3 | Metric scale and left-hand traffic | At J1 and J2 watch vehicles. | Vehicles drive on the **left**; cars about 4.5 × 1.8 m next to 3.5 m lanes; grid cells 100 m. | CLAUDE.md units; PS1 LHT | Both | P1 | |
| B4 | Lane flow toggle | Click **lane flow** (top-left), run ~2 min at 5×. | Lanes/connectors coloured by measured flow (dark blue → orange); **magenta = unused** (J1 surface through connectors with the flyover open); legend shown; toggling off hides it. | PS6 lane utilisation + exceptions; 5-min window | Both | P1 | |

## C. Simulation controls

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| C1 | Speeds | Click 1×, 2×, 5× (and 0.25×, 0.5× once). | Clock runs at the stated rate; vehicles move smoothly (no teleporting between frames). | PS2 interpolator; fixed dt 0.1 s | Both | P1 | |
| C2 | Pause and resume | Click ❚❚, wait 10 s, click 1×. | Clock and vehicles freeze, then continue from the same state. | PS2 | Both | P1 | |
| C3 | Header reset | Click **↺ reset**. | Same seed, same settings: run restarts; the clock is 0; vehicles refill. | PS5 resets (one reset function) | Both | P1 | |
| C4 | KPI panel plausibility | Run default for 3–5 min. | Flow per detector, queues at J1/J2, delay (n grows; "reference not ready" only briefly), unserved 0, generated = inserted + queued; numbers change, none are NaN/negative. | INV-4 conservation; PS5 F5 delay reference | Both | P1 | |

## D. Presets

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| D1 | Every preset loads | Preset dropdown: default, rush hour, flyover closed, J2 before; **Load preset (restarts)** each. | Each starts without error; the panel title follows; preset note text matches. | PS5 e2e "every preset"; PS3 presets | Both | P1 | |
| D2 | Rush hour vs default | Load default, note J1 queues after 5 min; load rush hour, same. | Rush hour (flows ×1.26, J1 flow ratio 0.85) has clearly longer J1 queues and more delay. | PS7/PS8 rush factor re-derivation | Both | P2 | |
| D3 | Flyover closed preset | Load it; run 5 min. | No vehicle on the deck/ramps; surface roads jam heavily; queue at J1 grows past the diverge; no crash. | PS6 flyover_closed exceptions; INV-5 | Both | P1 | |
| D4 | J2 before (one shared minor lane) | Load it; look at J2's minor road. | One minor approach lane (left and right turners share it); left-turners can be blocked behind a waiting right-turner. | README "Minor approach"; PS3 | Both | P3 | |

## E. Live settings

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| E1 | Change demand live | Edit a flow (e.g. West entry → E 1100 → 400), apply. | Applied at the next tick; the change log shows it; traffic on the arterial visibly thins; no collision or jump. | PS3 live changes; same seed + log ⇒ same run | Both | P1 | |
| E2 | Change vehicle mix live | Set e.g. 40% trucks/buses; apply. | New arrivals follow the mix; trucks (12 m) appear; the design saturation flows are not recomputed (documented). | PS5 F2 design flows; mix | Both | P2 | |
| E3 | Signal policy | Switch J1 policy: fixed Webster → max-pressure → thresholded max-pressure. | Signal panel shows the controller name; no two conflicting greens; switching mid-cycle finishes amber/all-red first. | PS3/PS4 signals; INV-2 | Both | P1 | |
| E4 | Close and reopen the flyover live | Click "Flyover is open · close it" (confirm), wait, "reopen it". | Closed: ramps/deck empty after vehicles clear, long trips re-route to the surface (those too near the diverge finish on it); reopened: traffic returns. Both changes in the log. No stuck vehicles. | PS3 flyover change; INV-5 grade separation; PS5 stranded-vehicle fix | Both | P1 | |
| E5 | Change log and replay | After E1–E4 note the log; export (G3), reset with the same seed and import. | Same log ⇒ identical KPIs at the same time. | INV-1 determinism; PS3 | Local | P2 | |

## F. Structural settings (apply on reset)

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| F1 | Pending marker and apply | Change surface lanes 2→3 (do not reset). | "pending until reset" shows; the running network is unchanged; header/panel reset applies it ("building" banner a few seconds). | PS5 F1 building banner; structure editor | Both | P1 | |
| F2 | The link follows the surface group | With 3 surface lanes, look east of J1 and at the lane drop. | The link east of J1 has **3 lanes** (same width), joins the flyover lanes at the merge, and the lane drop is 5→2; vehicles use the extra lane. | PS8 link change; README "Widths and capacities" | Both | P1 | |
| F3 | Extreme: 1 lane × 2.5 m both groups | Set 1/1 lanes, 2.5 m; reset; run 5 min. | Builds, runs, no overlap of lanes or vehicles, no collision, queues long but no deadlock. | PS5 144-structure tests; INV-2/3 | Both | P1 | |
| F4 | Extreme: 4 lanes × 4.0 m both groups | Set 4/4, 4.0 m; reset; run 5 min. | Builds (building banner), 8-lane sections render; no overlap; vehicles use the lanes. | PS5; lane utilisation (middle lanes are a documented exception) | Both | P1 | |
| F5 | J2 minor approach 1 vs 2 lanes | Set J2 minor = 1 lane, reset; then 2 lanes. | 1: one shared lane; 2: separate left and right lanes; both run. | PS3 J2 flared approach; `test_j2_minor_lanes` | Both | P2 | |
| F6 | Width alone | Flyover 2 × 3.5 m → 2 × 2.75 m; compare KPIs after 5 min. | Little change in queues/throughput; vehicles on the flyover a bit slower (lane-width speed model). | README "width alone has no significant effect" | Local | P3 | |
| F7 | Invalid structure values | Enter 0 or 5 lanes, 2.4 or 4.1 m. | An error next to the field; **nothing is clamped**; reset is disabled while invalid. | PS5 validation | Both | P2 | |

## G. Seed, replay, export / import

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| G1 | Same seed replays | Seed 7, "Reset with these settings", note KPI at t = 2:00; repeat. | Identical numbers (flow, queues, delay). A different seed gives different numbers. | INV-1 determinism | Both | P1 | |
| G2 | Seed field editing | Click into the seed, **Backspace** until empty, type 123. | The field really empties (it used to refill with the running seed); empty shows the error; 123 accepted. | PS9 seed bug fix | Both | P1 | |
| G3 | Export and import round trip | **Export JSON**, then **Import JSON** of that file. | A scenario file downloads; importing gives the same settings, seed and change log. | PS3 scenario JSON v1 | Both | P1 | |
| G4 | Bad import | Import a file with `"mix"` shares summing to 97, and a non-JSON file. | Errors with a path (e.g. `initial.mix: shares sum to 97, must be exactly 100`) or "not valid JSON"; the running sim is untouched. | PS3 scenario validation | Both | P2 | |

## H. Charts (results drawer)

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| H1 | MFD | Click **results**, tab MFD, run 5× for 2–3 min. | One point per 10 simulated s, rising density/flow cloud; points cyan (flyover open); newest point biggest. | PS7 Edie MFD | Both | P1 | |
| H2 | Space-time | Tab space-time; switch eastbound/westbound and surface/flyover. | Speed colour field; red bands at J1 (queue) moving upstream on the surface route; J1/J2 marked; flyover route mostly free flow. | PS7 corridor meter | Both | P2 | |
| H3 | Queues | Tab queues. | J1 and J2 lines grow and fall with the signal cycle; values agree with the right-panel queues. | PS7; KPI queue definition | Both | P2 | |
| H4 | Closure shows up | With charts open close the flyover (E4). | MFD points turn amber and shift to higher density, lower flow; J1 queue line climbs. | PS7 | Both | P2 | |
| H5 | Close the drawer | Click **results** again; frame rate unaffected. | Drawer gone; the server stops sending chart data (no console error). | PS7 charts stream on/off | Both | P3 | |

## I. Vehicle inspector

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| I1 | Pick a vehicle | Use the J1 view; click a vehicle. | Yellow box on it; panel with class, trip (O→D), lane, speed, acceleration, delay so far, lane changes, route, IDM and MOBIL parameters; values update ~4×/s. | PS7 inspector | Both | P1 | |
| I2 | Follow | Click **follow**. | Camera tracks it keeping the offset; unfollow/Esc returns control. | PS7 follow camera | Both | P2 | |
| I3 | Closing cleanly | Wait until the vehicle leaves the network; also Esc and the ✕ button. | "Left the network at t = …", panel closes by itself after ~3 s; Esc and ✕ close it at once; **no error in the console**; a reset closes it. | PS7 inspector; deselect fix | Both | P1 | |

## J. Compare

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| J1 | Five built-in experiments | Compare tab, open each: policy, flyover open/closed, surface lanes closed, flyover width, flyover lanes. | Each loads instantly; table with intervals and verdicts; **travel-time histogram + box plots** above; none marked stale. | PS7/PS8 experiments; METRICS_VERSION 3 | Both | P1 | |
| J2 | Results agree with the README | Check three numbers against README "Widths and capacities". | Flyover 2 vs 1 lane: delay about +105 s, throughput about −1,300 veh/h; width alone: delay not significant, p50 about +17 s; surface closed 3 vs 2 lanes: throughput about −990 veh/h. | PS8 | Both | P1 | |
| J3 | Honest labelling | Open "flyover open vs closed". | Completed-trip rows are explained as survivorship; unfinished/unserved rows shown; "flyover share" undefined; the note about multiple comparisons. | PS5 F4/F5; README reading notes | Both | P2 | |
| J4 | A vs A | Custom comparison, both sides "default", 3 runs. | Every metric "identical in every run" (zero variance, no verdict invented). | PS5 F4 zero variance; INV-1 | Both | P1 | |
| J5 | Hosted limits | (Live) Custom comparison: pick 5 runs or duration 900. | Defaults are 3 runs / 300 s / warm-up 60 s; larger values give "this server allows at most 3 runs / 300 s"; a second job while one runs is refused as busy. A 3-run job can take ~15 min. | PS9 hosted compare limits | Live | P1 | |
| J6 | Custom comparison locally | (Local) Default vs rush hour, 3 runs, 300 s, warm-up 60 s. | Progress bar, result table, runs cached on a second try. | PS3 compare service | Local | P2 | |

## K. Validation tab

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| K1 | All items | Open **Validation**. | 8 cards (ring waves, lane capacity, stop-line discharge, J2 left, J2 right, Webster, 2 known differences), each with measured, reference, source, reproduce command; copy button works; no "stale" message. | PS7 validation tab | Both | P1 | |
| K2 | Differences are shown, not hidden | Read the J2 left-turn and stop-line cards. | Stop-line −14% vs HCM and J2 left turn 146% of HCM are shown as differences (orange), with the explanation; ring waves "agrees". | PS7; README known differences | Both | P2 | |

## L. Hosted limits and session handling (live site)

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| L1 | Two seats, third tab is busy | Open the site in 3 tabs (or 2 devices + 1). | First two run; the third shows the friendly busy text ("free server allows 2 live simulations … try again in a minute … Compare and Validation still work") and retries by itself every 15 s. Compare/Validation work in that tab. | PS9 load test; busy message | Live | P1 | |
| L2 | A closed tab frees its seat | With 2 seats used, close one tab; reload the busy one. | It gets a seat within seconds. `/api/health` `sessions_active` falls; `sessions_closed` counts the end. | Slot-release fix (`liveness`), `test_liveness` | Live | P1 | |
| L3 | A vanished connection frees its seat | Start a session, then switch off the network (airplane mode) for 40 s, restore. | Within ~30 s the server frees the seat; the page reconnects (or shows offline then connects). Never "busy" with one tab. | Heartbeat 30 s; PS9 busy-with-one-tab bug | Live | P1 | |
| L4 | Idle pause and resume | Leave a tab open and untouched (no mouse/keys) for 10 minutes. | "Paused after 10 minutes without activity. Click to resume" with a **Resume** button; the seat is freed; Resume starts a new run. | PS9 idle timeout | Live | P2 | |
| L5 | Speed on the hosted server | Try 5× and 10×. | 5× runs choppily; **10× is slow** (about 2 frames/s: documented, 0.1 CPU). Nothing crashes; other seat unaffected. | README load test | Live | P2 | |
| L6 | Health shows sessions | Watch `/api/health` while opening/closing tabs. | `sessions_active`, `session_ages_s`, `sessions_closed` change accordingly. | PS9 | Live | P2 | |

## M. Invalid inputs

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| M1 | Bad demand values | Enter negative, text, and a huge number (1e9) in a flow. | Error next to the field or a rejected change with a message naming the limit; the sim keeps running; nothing clamped silently. | PS5 F9 size limits; PS3 validation | Both | P1 | |
| M2 | Mix not summing to 100 | Edit shares so they sum to 97. | Clear error; Apply disabled or rejected with the path. | PS3 scenario schema | Both | P2 | |
| M3 | Decimal total-demand input | Type "1530.5" into a *total* demand field. | **Known open issue (PS5 F10):** typing a decimal point may not work; record what happens. | PS5 F10 (still open) | Both | P3 | |

## N. Robustness

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| N1 | Refresh mid-run | Run 2 min, press F5. | New session, clock restarts at 0, no stuck banner, no seat leak (health). | Slot release; reconnect | Both | P1 | |
| N2 | Two tabs | (Local) open two tabs, change settings in one. | Sessions are independent (each has its own simulation and log). | PS2 per-session sim | Local | P2 | |
| N3 | Hidden tab | Switch to another tab for 70+ s, come back. | The socket closed after 60 s hidden and reconnects when visible; a fresh run; no error. | PS2 hidden-tab disconnect | Both | P3 | |
| N4 | Reset while building | Apply a new structure (building banner), press reset again quickly. | "still building … try again" message or a clean second build; no exception, old sim keeps running meanwhile. | PS5 F1 | Both | P2 | |
| N5 | Server restart | (Local) kill and restart uvicorn while a tab is open. | Page shows offline, reconnects with back-off, then runs. | PS2 reconnect | Local | P3 | |

## O. Visual realism and behaviour

| # | Scenario | Steps | Expected | Relates to | Where | Prio | Result |
|---|---|---|---|---|---|---|---|
| O1 | Stops at red, no running | At J1 for several cycles. | Queues stop **before** the stop line on red; nothing enters on red or when the exit is full; no vehicles stopped inside the box. | INV-3 spillback guard; signals | Both | P1 | |
| O2 | Give-way at J2 | At J2 watch the minor road. | Minor vehicles wait for a gap; right-turners (crossing) wait longest; no entry into a gap shorter than the critical gap; no overlap in the box. | PS3 gap acceptance; Validation J2 | Both | P1 | |
| O3 | Lane drop merge | "lane drop" view at rush hour. | Link lanes end at x = 900 m; vehicles change lanes before the end (hatched taper), none stuck at the end of a dropped lane, none teleport. | PS5/PS8 lane drop; stranded-vehicle fix; lane planning | Both | P1 | |
| O4 | Trucks on the ramp | Raise trucks to 40%; flyover view. | Trucks (12 m) climb the ramp slowly with cars behind them; cars overtake on the 2-lane deck; trucks keep their lane. | PS1 power-to-mass; MOBIL | Both | P2 | |
| O5 | No overlaps, no collisions | Watch busy places at 1× (J1, merge, J2, deck). | No vehicle boxes overlap; lane changes are smooth (lateral blend), never a jump; speeds never negative. | INV-2; `frames.py` lane-change blend | Both | P1 | |
| O6 | Overtaking and return | On the 4-lane west road, watch a car pass a truck. | Passes in the median-side lane and **returns to the kerb lane** after; lanes all used, kerb lane busiest. | Keep-left bias 0.12 (PS6); `test_lane_changes` | Both | P2 | |
| O7 | Flyover is grade separated | Watch under the deck at J1 and the ramps. | Deck traffic never interacts with surface traffic; vehicles change level only via the ramps; clearance visible. | INV-5 | Both | P1 | |
| O8 | Turn lanes and movements | At J1 follow cars from each arm. | Kerb lane turns left, last lane turns right, others go straight; no vehicle ends in a turn-only lane when it needs to go straight. | PS8 lane planning one road ahead; PS6 | Both | P2 | |

---

### Known limitations to keep in mind while testing (not failures)
- J2 right turn serves almost nothing at rush hour (gap acceptance); the default serves about 14 veh/h (README Known differences).
- Hosted instance: 2 seats, 10× unusable, custom compare ≤ 3 runs / 300 s and slow; keep-alive pings every 5 min.
- The default network has a **4→2** lane drop and no 3-lane road (the link follows the surface lanes).
- Merge rule at junction exits is "by green" (known zipper limitation, README); not visible at J1 with the new link.
- PS5 F10 (decimal point in the total-demand field) is still open.

### Result summary (fill in)
P1 passed: __ / __  ·  P2 passed: __ / __  ·  P3 passed: __ / __  ·  Date: ______  ·  Tester: ______
