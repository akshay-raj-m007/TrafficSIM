# TrafficSIM — project state 4: what is not built, and what could break

Continues `project_state_3.md`. Written 7 Nov 2026 after reading through the code added in step 3
and 4a and testing the suspect spots. Findings marked **confirmed** were reproduced by running
them; the rest are read from the code and say so.

## 1. Features not written yet

| # | Feature | Notes |
|---|---|---|
| 1 | **Lane counts and widths of the main roads as structural settings** (applies on reset) | Planned in step 3 Part 4, moved behind 4a. Lane-level links in `network/demo_corridor.py` and the J1/J2 turn rules in `network/demo.py` are written for F=2 flyover lanes, S=2 surface lanes. Needs: a frozen `Structure`, generated turn rules per approach, J1 box / J2 plate sizes from widths, an exact-equality test for the default, invariant runs on every variant, and **free-flow and calibration tables per structure** (today two committed variants; arbitrary structures would measure ~100 s + 8 s each). The panel says "not editable yet". |
| 2 | **4b: charts, vehicle inspector, validation tab** | Requested for the next step. Charts would also be the place to show the warm-up settling check (vehicle count / delay over time) that the 300 s default rests on only by the 242 s free-flow argument. |
| 3 | Deployment (Render / Docker) with compare limits | Parked by decision. A 10-run comparison is ~10 CPU-minutes, about 1.6 h at 0.1 CPU; only the precomputed built-ins are viable there. |
| 4 | Per-class / per-route delay in comparisons | `CLAUDE.md` promises delay "per class, per route"; the live KPI aggregates, and the comparison reports pooled metrics only. |
| 5 | Comparison extras | Export of a result (JSON/CSV), custom seed list, comparing more than two scenarios in the UI (the built-in policy experiment does three pairwise comparisons offline), multiple-comparison adjustment (today only a note), a normality / outlier check for small n. |
| 6 | Browser tests in the repo | The Playwright scripts live in the session scratchpad, not in the repository; React components are untested apart from pure logic (see finding F1). |
| 7 | Known display limits (README) | Lane-change blend can overlap neighbours visually; real 60 fps unverified (headless software GL gave ~27 fps); two-wheelers do not filter between lanes. |

## 2. Audit: what could break in the logic

**Fixed during this audit**

- **F0 (confirmed, fixed): loading the one-lane J2 preset desynchronised the UI.** The hello of
  the restarted session arrived before the matching network had been fetched;
  `LanePlacer` threw "polyline length 385 differs from 388" inside `onHello`, so the hello was
  never applied (panel stayed on "2 lanes" while the server ran the 1-lane network). Now
  `tryBuildPlacer` returns null until the network matches (Vitest case added); the browser run
  shows structure "1" and no errors. Why it escaped: no component-level or browser test in the
  repo (item 6 above).

**Open (ordered by how much I would worry)**

| ID | Finding | Evidence | Impact | Suggested fix |
|---|---|---|---|---|
| F1 | **A live reset (or policy switch) with a non-default vehicle mix blocks the server for ~8 s.** `Simulation.__init__` / `switch_policy` call `make_controllers`, which measures saturation flows when the mix is not the committed default; this runs on the asyncio event loop in `LiveSession._reset` / `_apply`. | **confirmed**: init 0.41 s with the default mix, 7.88 s with another | every session on that worker freezes (no frames, ping timeouts); critical when hosted | run the simulation build in a thread (as `_warm_up` does) and show "preparing"; cache calibration per mix |
| F2 | **A live mix change does not update the saturation flows / start-up losses** that Webster and max-pressure use; they stay those of the initial mix. | **confirmed**: max-pressure's saturation flow is 962.0 before and after a 50% truck mix change | after a big mix change the controllers act on stale capacities (modelling honesty, README states "measured") | recalibrate on `SetMix` (off-loop) or state the limitation next to the mix control |
| F3 | **Run cache and shipped results are keyed by constants and network, not by engine logic.** Editing e.g. `gates.py` leaves stale entries in `backend/.cache/compare` and in the shipped files valid-looking. | read from `compare_spec.run_key` (digest = `freeflow.input_digest`); the slow replay test `test_a_stored_run_is_reproduced_exactly_by_the_current_engine` and CI catch shipped files only | silent wrong numbers in local comparisons after an engine edit | add a hash of the engine/network sources to the key; clear the cache directory on mismatch |
| F4 | **Degenerate paired interval:** if every per-seed difference is the same non-zero number (sd = 0), the row says "significant" with CI [d, d] and p = 0. | **confirmed**: A = 10,20,30, B = 11,21,31 gives significant, p 0.0 | possible with count metrics on few runs; overstates certainty | report "constant difference, no spread" instead of a verdict, or require sd > 0 |
| F5 | **Delay reference differs between vehicles rerouted by a live closure and vehicles inserted after it** (original-route reference vs closed-route reference). | read from `changes.py` / README | a comparison with a *mid-run* closure mixes two meanings of delay; closed-from-start comparisons (the built-ins) are clean | keep mid-run closures out of A/B headlines or state it beside them |
| F6 | **Compare jobs:** when one run raises, the other submitted runs keep computing but the job leaves "running", so the job cap can be exceeded; cancel only takes effect when the next run finishes (up to ~30 s) and cannot stop a running task; finished jobs are never pruned; the pool is not shut down in the app lifespan. | read from `compare_jobs.py` | resource leak / cap bypass under errors; minor locally | cancel remaining futures on error; prune old jobs; shutdown in lifespan |
| F7 | **Pool workers compete with live sessions** (default min(4, cores-1) processes on the same host). | by construction; compare run took all cores for ~3 min here | live frame lag while a comparison runs; severe on a small host | lower default workers when sessions are active, or `nice` the workers |
| F8 | **No bounds on live changes:** `Simulation.schedule` accepts a tick beyond the end (never applied), the change log and WebSocket message size are unbounded, no rate limit; every `apply` can add reroute entries. | read from `loop.py`, `protocol.py` | memory / CPU abuse on a hosted server | cap log length and message size |
| F9 | **Header "reset" keeps the initial settings (drops live edits); the panel's "Reset with these settings" folds them in.** | read from `ws._reset` (`with_seed`) vs `restartDoc` | surprising on first use | make both behave the same, or label the header button |
| F10 | Total-demand input of an origin cannot take a decimal point while typing (it only accepts complete numbers). | read from `DemandEditor.tsx` | minor UX; per-destination fields are fine | keep raw text in state |
| F11 | Interpolation along the lane graph searches at most 5 segments; after a long gap between frames (dropped frames, tab in background) it falls back to a chord. | read from `laneGeometry.ts` | brief corner-cutting only | none needed, or raise the limit |
| F12 | `unserved_veh` counts all vehicles waiting at the end, `unfinished_veh` only the cohort. | read from `runmetrics.py` | two different bases next to each other (documented in the README) | add the basis to the label |
| F13 | J2 default demand: left turn 214 veh/h exceeds the capacity of the weakest measured seed (180). | measured (README) | that seed's J2 minor queue grows | by design (0.8 x mean); mention in the UI hint |

**Modelling behaviour worth remembering (not bugs)**

- J1's policy cannot change anything at J2 in these scenarios: everything reaching J2 comes over
  the flyover (W-E, E-W, W-N2, N2-W), so J2 rows are *identical* across policies in the
  experiments. If the demand pattern changes (surface through traffic), this stops being true.
- Reopening a flyover sends every queued vehicle upstream of the diverge onto it at once (6,240
  veh/h burst), and the J1 queue had not recovered 12 minutes later.
- With the flyover closed the westbound surface queue grows back through J2; travel-time
  percentiles of completed trips are survivorship-biased in overloaded scenarios (shown beside
  the unfinished counts).
- Cohort rule, warm-up, lower-bound delay are choices fixed before any result; a different choice
  moves overloaded-scenario numbers.

## 3. What I checked and found sound

- **Determinism / live changes:** replays through the change log give identical per-step hashes;
  live scheduling equals replay; the invariant harness (collision, conflict points, conservation)
  holds through close and reopen at 1.5x demand (min gap 0.658 m, 0 emergency brakings, 0
  box-held vehicle-seconds).
- **Paired seeds:** arrival lists are identical across signals, flyover state and mid-run
  changes (test); `behaviour` stream is unused.
- **Statistics:** quantile, CDF, p-values and intervals equal SciPy to 1e-8; hand example in the tests.
- **Cross-platform reproducibility:** the stored experiment run is reproduced bit-for-bit by the
  Linux CI runner (CI success on the latest pushed commit, 09a8e35 and earlier).
- **Cache layering and keys:** same comparison twice is a pure cache hit; A vs A computes each
  run once and gives zero difference on every metric; pool results equal inline results.
- **Process:** full backend suite 397 passed; frontend lint clean, 68 tests, build OK.
