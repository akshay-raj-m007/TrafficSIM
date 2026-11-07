# TrafficSIM — project state 5: the fix round, structural settings, browser tests

Continues `project_state_4.md` (audit). Written 7 Nov 2026.

## Audit findings: status

| ID | Decision | Status |
|---|---|---|
| F1 | build off the main loop, "building" state, cache measured tables by mix | **done**: sessions build in a worker thread (`server/session_build.py`, `ws.py`); `building` message and banner; a failed build ends the state with an error message; tables cached on disk by digest (`engine/tablecache.py`); compare jobs have a "preparing" phase. Reset with a 50%-truck mix: 9.9 s the first time (another session's longest frame gap 192 ms against a median 96 ms), 0.1 s afterwards, also in a new server process (disk cache) |
| F2 | signal plans keep their **design** saturation flows (design decision) | **done**: `JunctionDesign` built at reset (initial mix, initial demand); live mix/demand changes never touch it; documented in README and next to the mix inputs |
| F3 | hash of engine source in the cache key | **done** (`engine/sourcedigest.py`, LF-normalised); test: a changed digest misses the cache |
| F4 | zero variance | **done**: "constant difference across seeds, no variance, the confidence interval isn't meaningful", no p, no verdict (backend + Vitest) |
| F5 | delay against the fastest route on the fully open network (design decision) | **done** (`DelayReference`, `RouteTable.pair`); a lone car forced onto the surface shows 27 s of delay; METRICS_VERSION 2 |
| F6 | job cap with failed runs | **done**: a failed or cancelled job is "stopping" and counts against the cap until its started runs finish |
| F7 | workers compete with live sessions | **left, noted** (min(4, cores-1) workers) |
| F8 | bounds / rate limits for hosting | **left for the hosting step**; only the sizes in F9 were added |
| F9 | size limits | **done**: WebSocket message 256 KB, 500 live changes, 1 MB REST body (413), change after the end of the run is an error |
| resets | header and panel the same | **done**: one App function; a seed-only server `reset` folds the live changes |
| F10 | total-demand input cannot take a decimal point while typing | **still open** |
| F11, F12, F13 | chord fallback after long frame gaps; unserved vs unfinished bases; J2 left-turn default above the weakest seed's capacity | unchanged |

## New in this round
- **Structural settings** (`network/structure.py`, `demo_geometry.py`, `demo_corridor.py`, `demo.py`):
  surface group and flyover group, 1-4 lanes per direction, 2.5-4.0 m, J2 approach; default
  reproduced exactly (fingerprint fixture from the pre-change code); all 144 combinations and 16
  corners build and route; invariants hold on the extremes and mixed combinations; editor with
  validation and a "pending until reset" marker.
- **Browser smoke tests** (`frontend/e2e`, Playwright, CI job `e2e`): load, every preset, flyover,
  live changes + export, lane/width extremes + both resets, compare (stored experiment and a small
  live run). Any console error or page error fails a test.
- Documentation, the experiment results regenerated (delay reference and source digest changed),
  `tools/compare_structures.py`.

## Bugs found while doing it (all fixed)
1. **Browser tests found three real bugs**: the Preset dropdown reset to "default" after every
   restart (the panel remounts); a failed build left the UI on "Building..." forever (the server's
   `error` message was ignored); the KPI detector layout assumed the default arm length, so a wide
   structure failed to build ("detector J1_N: s = 350 m must lie in [20, 342.2]").
2. The fixed 3.0 m J1 link lane overlapped the ramp when the flyover group is narrower than 3.0 m:
   it now narrows to the flyover width.
3. The J2 critical-gap tables only exist for 1 or 2 lanes per direction (HCM); wider majors use
   the four-lane values (documented).

## Not done / open
- **4b**: charts, vehicle inspector, validation tab.
- Hosting: F7, F8, per-IP limits, a smaller default worker count, a persistent job store.
- Per-class / per-route delay in comparisons; comparison export; more than two scenarios in the UI.
- The CI `e2e` job has only run locally (Chrome); its first run on GitHub (Chromium on Ubuntu,
  software GL) is unverified.
- Any engine or network edit makes the shipped experiments stale (source digest): regenerate with
  `python tools/gen_experiments.py` (about 12 min on 4 cores) before pushing.
- A new structure costs about 60 s of background CPU for its free-flow reference the first time on
  a machine (delay shows "reference not ready" meanwhile), plus 5-10 s of saturation-flow
  measurement while building.
- `D:\tmp_measure` (server logs and a table cache from the reset-time measurement) can be deleted.

## Results of this round
- Reset with a non-default mix: 9.9 s first time (off the main loop), 0.1 s cached.
- Surface road 3 lanes x 3.5 m against 2 lanes x 2.75 m, rush hour, 10 runs: no meaningful
  difference (delay -0.7 s [-1.6, +0.2]; throughput 0 [-21, +21]); flyover group 2 lanes against 1:
  delay +90.5 s [+76.7, +104.4], throughput -944 veh/h.
- Tests: backend 476 passed (full), frontend 72, lint clean, browser tests pass locally.
