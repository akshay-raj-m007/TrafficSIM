import { useEffect, useRef, useState } from 'react';
import { fetchNetwork } from './api/network';
import { SimSocket, type ConnStatus } from './api/simSocket';
import type { HelloMsg, NetworkData, TickMsg } from './api/types';
import { SceneView } from './scene/SceneView';
import { Header } from './ui/Header';
import { ScenarioPanel } from './ui/ScenarioPanel';
import { TelemetryPanel } from './ui/TelemetryPanel';

export interface LiveState {
  status: ConnStatus;
  statusDetail?: string;
  hello?: HelloMsg;
  tick?: TickMsg;
  rateHz: number;
  rttMs?: number;
}

export function App() {
  const [network, setNetwork] = useState<NetworkData | null>(null);
  const [netError, setNetError] = useState<string | null>(null);
  const [live, setLive] = useState<LiveState>({ status: 'connecting', rateHz: 0 });
  const sockRef = useRef<SimSocket | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchNetwork(ctrl.signal)
      .then(setNetwork)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setNetError(String(e));
      });
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    const sock = new SimSocket({
      onStatus: (status, statusDetail) => setLive((s) => ({ ...s, status, statusDetail })),
      onHello: (hello) => setLive((s) => ({ ...s, hello })),
      onTick: (tick, rateHz) => setLive((s) => ({ ...s, tick, rateHz })),
      onRtt: (rttMs) => setLive((s) => ({ ...s, rttMs })),
    });
    sockRef.current = sock;
    sock.connect();
    return () => sock.dispose();
  }, []);

  return (
    <div className="app">
      <Header
        live={live}
        onSpeed={(k) => sockRef.current?.setSpeed(k)}
      />
      <ScenarioPanel
        network={network}
        seed={live.hello?.seed}
        onReset={(seed) => sockRef.current?.reset(seed)}
        disabled={live.status !== 'open'}
      />
      <main className="centre">
        <SceneView network={network} />
        {live.status === 'busy' && (
          <div className="banner banner--busy" role="alert">
            {live.statusDetail} Retrying automatically every 15 s.
          </div>
        )}
        {netError && (
          <div className="banner banner--error" role="alert">
            Could not load the network: {netError}
          </div>
        )}
      </main>
      <TelemetryPanel live={live} />
    </div>
  );
}
