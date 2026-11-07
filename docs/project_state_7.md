# TrafficSIM — project state 7: results made visible (step 4b)

Continues `project_state_6.md`. Written Sat 7 Nov 2026, evening. **Deadline: Mon 9 Nov 2026, 18:08 IST** (about 45 h left
when this was written).

## What was done
1. **Third built-in experiment** `surface_closed`: flyover closed, rush hour, surface 3 x 3.5 m against 2 x 2.75 m, 10
   paired runs (`server/experiments.py`, README "Built-in experiments"). Result: no benefit from the third lane (delay
   +2.9 s [+1.8, +4.1], throughput +44 veh/h [-7, +95] for the narrower road); J1 queues are shorter with 2 lanes,
   68 vehicles per run wait at the entries. Cause: both through lanes feed the single 3.0 m link lane east of J1
   (through flow at J1: 330 veh/h with 3 lanes, 492 with 2).
2. **Bug found by that experiment, fixed**: a through lane merging into a shared exit lane could be starved for ever
   (0 veh/h from a queue of 65 vehicles). `engine/merge_turns.py`: lanes that merge take turns by green. A first,
   vehicle-by-vehicle version cut the discharge by more than half and was dropped. Default-structure runs are unchanged
   (the policy and flyover experiment tables are identical to before); only structures with 2+ through lanes into one
   exit lane change.
3. **Charts** (results drawer): MFD (Edie, per lane, flyover open/closed colouring), space-time speed (10 m x 1 s cells,
   surface/flyover x eastbound/westbound, J1/J2 marked), J1/J2 queues. `engine/charts.py`, `charts` WebSocket stream only
   while open, 1 Hz. Meter cost 5.4% of step time (target was 3%, not optimised). fps with the drawer closed/open in the
   README.
4. **Compare**: pooled travel-time histograms and box plots (`server/compare_dist.py`, `METRICS_VERSION` 3).
5. **Vehicle inspector**: click to pick, highlight, panel with engine state, follow camera, closes on exit / Esc / reset.
   `server/inspector.py`, `ui/InspectorHost.tsx`, `scene/picking.ts`.
6. **Validation tab**: `tools/gen_validation.py` -> `data/validation.json`; six measured items and two documented ones, each
   with measured value, reference, source, command. New finding: J2 left turn serves 146% of HCM's formula on the current
   two-lane approach (the old 156-vs-287 table was for the shared lane).

## Tests
Backend 537 passed + the fixed compare test (539 collected with the new ones); Vitest 91; Playwright 10 (charts, inspector,
validation, compare distributions added; the inspector test was flaky twice and was fixed: deselect was not immediate, the
camera stayed on the followed vehicle). `tests/test_validation_doc.py` and `tests/test_experiments.py` fail when the stored
files are stale (regenerate: `tools/gen_validation.py` about 2 min, `tools/gen_experiments.py` about 12 min,
`tools/gen_calibration.py` / `gen_freeflow.py`).

## Decisions
- No decision of the user's was changed this round. (The keep-left bias of the previous round was accepted by the user.)
  Standing rule: if a decision of the user's fails a test, ask before changing it.

## Open / not done
- Meter overhead above the 3% target; a 5 Hz sampling variant would halve it but changes the definition slightly.
- e2e: once a test waited about 2 minutes because the server was at its two-session cap while the previous page closed.
- F10-F13 of `project_state_5.md` unchanged. Deployment parked. `D:\tmp_measure` leftover.
