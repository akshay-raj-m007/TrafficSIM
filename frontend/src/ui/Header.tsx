import type { ConnStatus } from '../api/simSocket';
import { formatClock } from '../api/protocol';

const DEFAULT_SPEEDS = [0, 0.25, 0.5, 1, 2, 5, 10];

export interface HeaderProps {
  status: ConnStatus;
  tick: number;
  agents: number;
  speeds?: number[];
  speed?: number;
  stepsPerSecond?: number;
  seed?: number;
  done?: boolean;
  onSpeed(speed: number): void;
  onReset(seed: number): void;
}

const STATUS_TEXT: Record<ConnStatus, string> = {
  connecting: 'connecting…',
  open: 'live',
  busy: 'server busy',
  closed: 'offline',
};

const label = (k: number) => (k === 0 ? '❚❚' : `${k}×`);

export function Header(p: HeaderProps) {
  const speeds = p.speeds ?? DEFAULT_SPEEDS;
  const enabled = p.status === 'open';
  return (
    <header className="header">
      <div className="brand">
        <span className="brand__name">TrafficSIM</span>
        <span className="brand__sub">agent-based traffic workbench · IDM + MOBIL</span>
      </div>
      <div className="speed" role="group" aria-label="Simulation speed">
        {speeds.map((k) => (
          <button
            key={k}
            type="button"
            className={k === p.speed ? 'is-active' : ''}
            disabled={!enabled}
            onClick={() => p.onSpeed(k)}
            title={k === 0 ? 'Pause' : `${k}× real time`}
          >
            {label(k)}
          </button>
        ))}
        <button
          type="button"
          disabled={!enabled}
          onClick={() => p.onReset(p.seed ?? 42)}
          title="Restart the simulation with the same seed"
        >
          ↺ reset
        </button>
      </div>
      <div className="agents" title="Vehicles currently on the network">
        <span className="clock__label">agents</span>
        <span className="clock__value">{p.agents}</span>
      </div>
      <div className="clock" title="Simulated time (fixed step dt = 0.1 s)">
        <span className="clock__label">sim clock{p.done ? ' · finished' : ''}</span>
        <span className="clock__value">{formatClock(p.tick, p.stepsPerSecond ?? 10)}</span>
      </div>
      <div className={`status status--${p.status}`}>
        <span className="status__dot" />
        {STATUS_TEXT[p.status]}
      </div>
    </header>
  );
}
