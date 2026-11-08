# TrafficSIM — project state 10: fast layout changes on the free tier

Continues `project_state_9.md`. Sun 8 Nov 2026. **Deadline: Mon 9 Nov 2026, 18:08 IST.**

- Measured at 0.1 CPU (real image): new structure = network 0.1 s, lane graph 0.0 s, saturation flows 154 s (blocking),
  setup 2.1 s, free-flow reference 1,011 s (background). Live 2 -> 4 lane reset before the change: 69 s.
- Fix: 78 structures' tables (all lane counts 1-4 x 1-4 at 3.5 m with both J2 variants; all widths 2.5-4.0 m by 0.25 m at
  2 + 2 lanes; default mix) precomputed by `tools/gen_structure_tables.py` (3,287 s on 6 workers) and shipped in
  `trafficsim/data/structures/` (0.72 MB). `tablecache.load` reads them before the writable cache; file names carry the
  input digest; `tests/test_structure_tables.py` guards staleness and reading without measuring.
- First-time layouts (a 3.1 m width, a custom mix): `building` message with `estimate_s` and step progress; banner
  "Preparing this layout for the first time, about N s (step k of 25)". Hosted `PREPARE_S_PER_STEP=6`.
- Found on the way: the 30 s heartbeat dropped a healthy client during a long build on 0.1 CPU (the loop was starved, the
  pings unread); `ws.py` now ignores a starved loop and re-checks (`test_a_blocked_server_loop...`).
- Engine source changed (calibration progress hook, tablecache): validation and the five experiments were regenerated,
  numbers unchanged.
- Environment note: the C: drive of the dev machine was 100% full (Docker VM disk 18 GB, DockerDesktopUpdates 3.3 GB);
  only own scratch files were deleted.
