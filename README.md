# TrafficSIM

Agent-based traffic simulator on a hand-built road network: two junctions (signalised and
give-way), a flyover with diverge/merge ramps, roads with 1–4 lanes, and a 3→2 lane drop.
It is meant to be used as a small research workbench.

- **Engine:** Python 3.12 + NumPy. IDM car-following and MOBIL lane changes (step 2), fixed
  `dt = 0.1 s`, seeded and deterministic. Tested with pytest.
- **Server:** FastAPI. Each browser session gets its own simulation, streamed over a WebSocket
  at 10 Hz. Concurrent sessions are capped, and extra visitors see a "server busy" message.
- **Frontend:** Vite + React + Three.js. A true metric 3D view (1 unit = 1 m) with scenario
  controls and measured telemetry.

> Status: **step 1 (baseline)**. Network, clock, streaming and 3D are in place. Vehicles, signals
> and KPIs arrive in step 2.

## Run locally

```bash
# backend (Python 3.12)
cd backend
py -3.12 -m venv .venv            # or: python3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python -m uvicorn trafficsim.server.app:app --port 8000

# frontend (Node 22+), in a second terminal
cd frontend
npm ci
npm run dev                        # http://localhost:5173 (proxies /api and /ws to :8000)
npm run lint && npm test && npm run build
```

Single-origin production image:

```bash
docker build -t trafficsim .
docker run --rm -p 8000:8000 trafficsim   # http://localhost:8000
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | status, `dt`, active / max / rejected sessions |
| `GET /api/network` | the network geometry (metres; x east, y north, z up) |
| `WS /ws/sim` | live session: `hello`, then `tick` frames; accepts `set_speed`, `reset`, `ping`. Returns `busy` and close code 1013 when full |

## Project rules

See [CLAUDE.md](CLAUDE.md) for module boundaries, units, the invariants that the tests
enforce, and the code rules.
