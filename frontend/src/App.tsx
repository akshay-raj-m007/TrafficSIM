import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchNetwork } from './api/network';
import { SimSocket, type ConnStatus } from './api/simSocket';
import type { HelloMsg, KpiMsg, NetworkData, StatsMsg } from './api/types';
import type { SceneManager } from './scene/sceneManager';
import { SceneView } from './scene/SceneView';
import { Header } from './ui/Header';
import { ScenarioPanel } from './ui/ScenarioPanel';
import { TelemetryPanel } from './ui/TelemetryPanel';

interface FrameInfo {
  tick: number;
  agents: number;
  speedIndex: number;
}

export function App() {
  const [network, setNetwork] = useState<NetworkData | null>(null);
  const [netError, setNetError] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnStatus>('connecting');
  const [statusDetail, setStatusDetail] = useState<string | undefined>();
  const [hello, setHello] = useState<HelloMsg | null>(null);
  const [kpi, setKpi] = useState<KpiMsg | null>(null);
  const [stats, setStats] = useState<StatsMsg | null>(null);
  const [frame, setFrame] = useState<FrameInfo>({ tick: 0, agents: 0, speedIndex: 3 });
  const [rateHz, setRateHz] = useState(0);
  const [rttMs, setRttMs] = useState<number | undefined>();
  const [pendingSpeed, setPendingSpeed] = useState<number | null>(null);
  const sockRef = useRef<SimSocket | null>(null);
  const sceneRef = useRef<SceneManager | null>(null);
  const speedsRef = useRef<number[]>([]);

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
      onStatus: (s, detail) => {
        setStatus(s);
        setStatusDetail(detail);
      },
      onHello: (h) => {
        speedsRef.current = h.speeds;
        sceneRef.current?.setSession(h);
        setHello(h);
        setKpi(null);
      },
      onFrame: (f, _now, rate) => {
        sceneRef.current?.pushFrame(f);
        setFrame({ tick: f.tick, agents: f.n, speedIndex: f.speedIndex });
        setRateHz(rate);
        setPendingSpeed((p) => (p !== null && speedsRef.current[f.speedIndex] === p ? null : p));
      },
      onKpi: setKpi,
      onStats: (s) => {
        setStats(s);
        setPendingSpeed((p) => (p !== null && s.speed === p ? null : p));
      },
      onRtt: setRttMs,
    });
    sockRef.current = sock;
    sock.connect();
    return () => sock.dispose();
  }, []);

  const onSpeed = useCallback((k: number) => {
    setPendingSpeed(k);
    sockRef.current?.setSpeed(k);
  }, []);
  const onReset = useCallback((seed: number) => sockRef.current?.reset(seed), []);

  const speeds = hello?.speeds;
  const frameSpeed = speeds?.[frame.speedIndex];
  return (
    <div className="app">
      <Header
        status={status}
        tick={frame.tick}
        agents={frame.agents}
        speeds={speeds}
        speed={pendingSpeed ?? frameSpeed}
        stepsPerSecond={hello?.steps_per_second}
        seed={hello?.seed}
        done={stats?.done}
        onSpeed={onSpeed}
        onReset={onReset}
      />
      <ScenarioPanel
        network={network}
        seed={hello?.seed}
        onReset={onReset}
        disabled={status !== 'open'}
      />
      <main className="centre">
        <SceneView network={network} classes={hello?.classes ?? []} managerRef={sceneRef} />
        {status === 'busy' && (
          <div className="banner banner--busy" role="alert">
            {statusDetail} Retrying automatically every 15 s.
          </div>
        )}
        {netError && (
          <div className="banner banner--error" role="alert">
            Could not load the network: {netError}
          </div>
        )}
      </main>
      <TelemetryPanel
        kpi={kpi}
        defs={hello?.kpi_defs ?? {}}
        rateHz={rateHz}
        rttMs={rttMs}
        stats={stats}
      />
    </div>
  );
}
