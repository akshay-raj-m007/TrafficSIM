import { useEffect, useRef, useState, type RefObject } from 'react';
import type { SimSocket } from '../../api/simSocket';
import type { HelloMsg } from '../../api/types';
import { ChartStore } from './chartStore';
import { MfdChart } from './MfdChart';
import { QueueChart } from './QueueChart';
import { SpaceTimeChart } from './SpaceTimeChart';

const TABS = ['MFD', 'space-time', 'queues'] as const;
type Tab = (typeof TABS)[number];

declare global {
  interface Window {
    /** Chart data as the browser holds it (for the browser tests). */
    __chartsDebug?: () => {
      open: boolean;
      mfd: ChartStore['mfd'];
      queue: ChartStore['queue'];
      cols: number;
      col0: number;
    };
  }
}

/**
 * The results drawer: a button over the 3D view and, when open, the charts of the measured
 * network state (MFD, space-time speed, queues). While it is closed the server sends nothing
 * (the `charts` stream is switched on and off with the drawer) and nothing is drawn; open, the
 * charts redraw once per message, about 1 Hz.
 */
export function ChartsHost({
  sock,
  hello,
}: {
  sock: RefObject<SimSocket | null>;
  hello: HelloMsg | null;
}) {
  const [store] = useState(() => new ChartStore());
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('MFD');
  const [version, setVersion] = useState(0);
  const openRef = useRef(open);

  useEffect(() => {
    const s = sock.current;
    if (!s || !hello) return;
    store.clear(); // a new simulation: the history starts again
    const off = s.on('charts', (m) => {
      store.push(m);
      setVersion(store.version);
    });
    if (openRef.current) s.setCharts(true); // a new session starts with the stream off
    return off;
  }, [sock, hello, store]);

  useEffect(() => {
    window.__chartsDebug = () => ({
      open: openRef.current,
      mfd: store.mfd,
      queue: store.queue,
      cols: store.cols.length,
      col0: store.col0,
    });
  }, [store, version]);

  const toggle = () => {
    openRef.current = !open;
    setOpen(!open);
    sock.current?.setCharts(!open);
  };

  return (
    <>
      <button
        type="button"
        className={`viewport__results ${open ? 'is-on' : ''}`}
        aria-pressed={open}
        data-testid="results-toggle"
        onClick={toggle}
      >
        results
      </button>
      {open && (
        <section className="chart" aria-label="Results charts" data-testid="charts">
          <div className="chart__tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={t === tab}
                className={t === tab ? 'is-active' : ''}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
            <span className="chart__note">measured by the server, last 10 min</span>
          </div>
          {tab === 'MFD' && <MfdChart store={store} version={version} />}
          {tab === 'space-time' && <SpaceTimeChart store={store} version={version} />}
          {tab === 'queues' && <QueueChart store={store} version={version} />}
        </section>
      )}
    </>
  );
}
