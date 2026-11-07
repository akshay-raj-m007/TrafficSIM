# TrafficSIM — project state 9: deployment preparation

Continues `project_state_8.md`. Written Sun 8 Nov 2026. **Deadline: Mon 9 Nov 2026, 18:08 IST.** Features frozen.

- Default network kept (user rule): a default with 1-, 2-, 3- and 4-lane roads needs 1 surface + 3 flyover lanes or
  3 surface + 1 flyover, i.e. a change of the `Structure` defaults and a full regeneration; not done.
- J2 right turn with no service at rush hour documented as expected behaviour (README, Known differences).
- Deployment: Docker image tested at 0.1 CPU / 512 MB. Found and fixed: the compare cache dir was not writable in the
  container (`COMPARE_CACHE_DIR=/tmp/trafficsim/compare`). Load test: 2 live seats at 1x; 10x unsustainable (one session
  2.4 frames/s). 100 users: 2 served, 98 busy, page and health fast. Hosted compare limits 3 runs / 300 s / 1 job / 1 worker
  (a job took 890 s). Wake-up banner after 4 s not connected (`frontend/e2e/waking.spec.ts`). Tools:
  `backend/tools/load_test.py`.
- Render steps are in the final message of the session; after the user sends the live URL: check health, websocket, 3D,
  compare, validation.
