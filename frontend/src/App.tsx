import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNetwork } from './api/useNetwork';
import { usePresets } from './api/usePresets';
import { SimSocket, type ConnStatus } from './api/simSocket';
import type { LiveChange, Problem, ScenarioDoc } from './api/scenarioTypes';
import type { BuildingMsg } from './api/messageTypes';
import type { HelloMsg, KpiMsg, StatsMsg } from './api/types';
import type { SceneManager } from './scene/sceneManager';
import { SceneView } from './scene/SceneView';
import { Banners } from './ui/Banners';
import { Header, type View } from './ui/Header';
import { downloadJson } from './ui/download';
import { Hosts } from './ui/Hosts';
import { CompareView } from './ui/compare/CompareView';
import { ScenarioPanel } from './ui/ScenarioPanel';
import { restartDoc } from './ui/scenarioDraft';
import {
  DEFAULT_STRUCTURE,
  checkStructure,
  structureToText,
  type StructureText,
} from './ui/structureDraft';
import { ValidationView } from './ui/validation/ValidationView';
import { TelemetryPanel } from './ui/TelemetryPanel';

interface FrameInfo {
  tick: number;
  agents: number;
  speedIndex: number;
}

export function App() {
  const [status, setStatus] = useState<ConnStatus>('connecting');
  const [statusDetail, setStatusDetail] = useState<string | undefined>();
  const [hello, setHello] = useState<HelloMsg | null>(null);
  const [kpi, setKpi] = useState<KpiMsg | null>(null);
  const [stats, setStats] = useState<StatsMsg | null>(null);
  const [frame, setFrame] = useState<FrameInfo>({
    tick: 0,
    agents: 0,
    speedIndex: 3,
  });
  const [rateHz, setRateHz] = useState(0);
  const [rttMs, setRttMs] = useState<number | undefined>();
  const [pendingSpeed, setPendingSpeed] = useState<number | null>(null);
  const [view, setView] = useState<View>('simulate');
  const [building, setBuilding] = useState<BuildingMsg | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [doc, setDoc] = useState<ScenarioDoc | null>(null);
  const [structureText, setStructureText] = useState<StructureText>(
    structureToText(DEFAULT_STRUCTURE),
  );
  const structureCheck = useMemo(() => checkStructure(structureText), [structureText]);
  const presets = usePresets();
  const [applyErrors, setApplyErrors] = useState<Problem[]>([]);
  const [resetErrors, setResetErrors] = useState<Problem[]>([]);
  const sockRef = useRef<SimSocket | null>(null);
  const sceneRef = useRef<SceneManager | null>(null);
  const speedsRef = useRef<number[]>([]);

  const { network, netError } = useNetwork(hello?.network ?? DEFAULT_STRUCTURE);

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
        setBuilding(null);
        setServerError(null);
        setDoc(h.scenario);
        if (h.scenario) setStructureText(structureToText(h.scenario.structure));
        setApplyErrors([]);
        setResetErrors([]);
        setKpi(null);
      },
      onApplied: (m) => {
        setApplyErrors([]);
        setDoc((d) => (d ? { ...d, changes: [...d.changes, m.change] } : d));
      },
      onRejected: (m) => (m.request === 'apply' ? setApplyErrors : setResetErrors)(m.errors),
      onScenario: (m) => downloadJson(m.scenario),
      onBuilding: (m) => setBuilding(m),
      onError: (m) => {
        setBuilding(null); // a failed build ends the building state; the old simulation runs on
        setServerError(m.message);
      },
      onFrame: (f, _now, rate) => {
        sceneRef.current?.pushFrame(f);
        setFrame({ tick: f.tick, agents: f.n, speedIndex: f.speedIndex });
        setRateHz(rate);
        setPendingSpeed((p) => (p !== null && speedsRef.current[f.speedIndex] === p ? null : p));
      },
      onKpi: (k) => {
        sceneRef.current?.setLaneFlow(k.lane_flow);
        setKpi(k);
      },
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
  // The one reset: keeps the live edits, applies the structure draft, takes the seed. The
  // header button and the panel button both call it.
  const onReset = useCallback(
    (seed: number) => {
      const s = structureCheck.structure; // an invalid draft never resets (buttons disabled)
      if (doc && s) sockRef.current?.resetTo({ scenario: restartDoc(doc, s, seed) });
      else if (!doc) sockRef.current?.reset(seed);
    },
    [doc, structureCheck],
  );
  const onApply = useCallback((c: LiveChange) => {
    setApplyErrors([]);
    sockRef.current?.applyChange(c);
  }, []);

  const speeds = hello?.speeds;
  const frameSpeed = speeds?.[frame.speedIndex];
  return (
    <div className={`app app--${view}`}>
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
        resetDisabled={structureCheck.structure === null}
        view={view}
        onView={setView}
      />
      <ScenarioPanel
        network={network}
        doc={doc}
        epoch={hello?.epoch ?? 0}
        presets={presets}
        applyErrors={applyErrors}
        resetErrors={resetErrors}
        stepsPerSecond={hello?.steps_per_second ?? 10}
        disabled={status !== 'open' || building !== null}
        onApply={onApply}
        structureText={structureText}
        onStructureText={setStructureText}
        resetDisabled={structureCheck.structure === null}
        onReset={onReset}
        onPreset={(name, seed) =>
          sockRef.current?.resetTo(seed === null ? { preset: name } : { preset: name, seed })
        }
        onExport={() => sockRef.current?.exportScenario()}
        onImport={(raw) => sockRef.current?.resetTo({ scenario: raw as ScenarioDoc })}
      />
      {view === 'validation' && <ValidationView />}
      {view === 'compare' && (
        <CompareView
          presets={presets}
          current={doc ? restartDoc(doc, doc.structure, doc.seed) : null}
        />
      )}
      <main className="centre">
        <SceneView network={network} classes={hello?.classes ?? []} managerRef={sceneRef} />
        <Hosts sock={sockRef} hello={hello} scene={sceneRef} />
        <Banners
          building={building}
          serverError={serverError}
          netError={netError}
          status={status}
          detail={statusDetail}
          onResume={() => sockRef.current?.connect()}
        />
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
