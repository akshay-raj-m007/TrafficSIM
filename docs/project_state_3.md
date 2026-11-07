# TrafficSIM — project state 3 (step 3: scenario setup, step 4a: A/B comparison)

Continues `project_state_1.md` (step 1, 2a) and `project_state_2.md` (2b + J2 fix). Written 7 Nov 2026.

## Done in this part
**J2 follow-ups.** README no longer says bunching is the main cause (the shared lane was; bunching
is a partial, unproven hypothesis). "Known differences from HCM" explains the right turn's 64% of
HCM: fewer usable gaps than random arrivals (52 vs 127 per hour at 980 veh/h conflicting, CV 1.77),
partly offset by longer gaps, follow-up headway 4.36 s vs 3.5 s (24.8 m, ~21 km/h path), small
start-up/unused-window losses. Nothing tuned.

**Webster with measured start-up loss.** L 25.5 to 35.8 s, C0 123.1 to 167.1 s, applied cycle 120 s
(C_MAX). Fixed a bug: greens now sum with intergreens to the cycle exactly.

**Frame format v2** (9 B/vehicle: id, segment, arc length cm, lateral 5 cm, speed, flags; hello has
the segment table). `frontend/src/scene/laneGeometry.ts` places vehicles on the lane graph; turns
follow the curve at 10x (1 mm vs 5.8 m chord). Fixtures `golden_frame.*`, `placement.json`.
Frame size at 159 vehicles: 1,440 B raw / 412 B deflated.

**Live changes** (`engine/changes.py`): SetDemand, SetMix, SetPolicy, SetFlyover; `Simulation.schedule`,
`change_log`, `Scenario.changes` replay; policy switch continues the current phase; flyover close
re-routes (also vehicles inside connectors), grandfathers vehicles too close to the diverge, keeps
the free-flow reference of the original route. Invariants hold through close/reopen at 1.5x demand
(`tests/invariants/test_flyover_change.py`).

**Scenario JSON** (`server/scenario_doc.py`), presets `default / rush_hour / flyover_closed /
j2_before`, WebSocket `apply / reset / export`, REST `/api/presets`, `/api/scenario/validate`,
`/api/network?j2_minor_lanes=`. Default J2 demand from measured capacities: left 214, right 37 veh/h
(0.8 x 268 and 46). Rush hour = x1.31 (J1 Y 0.649 to 0.850). Editor UI in the left panel.

**Step 3 reports** (README / chat): flyover close at 300 s and reopen at 780 s at rush hour, J2
before/after (two lanes: delay of N2 trips 38.7 vs 110.4 s mean over seeds 42, 1, 2).

**A/B comparison (4a).** `engine/runmetrics.py` (cohort rule, unfinished lower bound, queues,
flyover share), `engine/pairedstats.py` (paired t, df = n-1, checked against SciPy), `server/compare_*`
(process pool, per-run cache, job cap, config limits, REST), Compare tab, two precomputed
experiments in `trafficsim/data/experiments/`. Two extra committed table variants for the one-lane J2.
Cost: 572 CPU s (default demand) / 649 CPU s (rush hour) for 10 runs x 2 scenarios x 900 s; 150-171 s
wall on 4 workers.

## Not done / open
- Lane counts and lane widths of the main roads as structural settings (generalising the
  lane-level links and J1/J2 turn rules); the panel says "not editable yet".
- 4b: charts, vehicle inspector, validation tab.
- Deployment (Render/Docker) parked; the compare jobs need limits there.
- Real 60 fps rendering unverified (headless software GL ~27 fps).

## Commands added
```bash
python tools/gen_experiments.py [--cost]    # ~15 min on 4 cores; writes data/experiments/*.json
python tools/measure_j2_capacity.py         # J2 default demand from measured capacities (~50 s)
python tools/gen_golden_frame.py            # frame + placement fixtures
python tools/gen_freeflow.py / gen_calibration.py   # both J2 variants
```
