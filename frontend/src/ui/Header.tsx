import type { LiveState } from '../App';
import { formatClock } from '../api/protocol';

const SPEEDS = [0, 1, 2, 5, 10];

interface Props {
  live: LiveState;
  onSpeed(speed: number): void;
}

const STATUS_TEXT: Record<LiveState['status'], string> = {
  connecting: 'connecting…',
  open: 'live',
  busy: 'server busy',
  closed: 'offline',
};

export function Header({ live, onSpeed }: Props) {
  const speeds = live.hello?.speeds ?? SPEEDS;
  const current = live.tick?.speed;
  const enabled = live.status === 'open';
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
            className={k === current ? 'is-active' : ''}
            disabled={!enabled}
            onClick={() => onSpeed(k)}
            title={k === 0 ? 'Pause' : `${k}× real time`}
          >
            {k === 0 ? '❚❚' : `${k}×`}
          </button>
        ))}
      </div>
      <div className="clock" title="Simulated time (fixed step dt = 0.1 s)">
        <span className="clock__label">sim clock</span>
        <span className="clock__value">{formatClock(live.tick?.tick ?? 0)}</span>
      </div>
      <div className={`status status--${live.status}`}>
        <span className="status__dot" />
        {STATUS_TEXT[live.status]}
      </div>
    </header>
  );
}
