import { useEffect, useEffectEvent, useRef, useState, type RefObject } from 'react';
import type { VehicleLiveMsg, VehicleMsg } from '../api/messageTypes';
import type { SimSocket } from '../api/simSocket';
import type { HelloMsg } from '../api/types';
import type { SceneManager } from '../scene/sceneManager';
import { Inspector } from './Inspector';

/** How long the panel stays after the vehicle has left, and how often the readout refreshes. */
export const GONE_CLOSE_MS = 3000;
export const READOUT_PERIOD_MS = 250;

interface Props {
  sock: RefObject<SimSocket | null>;
  hello: HelloMsg | null;
  scene: RefObject<SceneManager | null>;
}

/**
 * Click a vehicle in the 3D view to inspect it: a highlight box, a panel with what the engine
 * knows (server/inspector.py) and a "follow" camera. The panel closes by itself a few seconds
 * after the vehicle leaves the network, on Esc, and when a new simulation starts (vehicle ids
 * belong to one simulation, so the inner component is remounted per simulation).
 */
export function InspectorHost({ sock, hello, scene }: Props) {
  if (!hello) return null;
  return <Selection key={`${hello.session_id}:${hello.epoch}`} sock={sock} scene={scene} />;
}

function Selection({ sock, scene }: Omit<Props, 'hello'>) {
  const [selected, setSelected] = useState<number | null>(null);
  const [live, setLive] = useState<VehicleLiveMsg | null>(null);
  const [goneAt, setGoneAt] = useState<{ t: number | null; laneChanges: number } | null>(null);
  const [follow, setFollow] = useState(false);
  const lastShown = useRef(0);
  const closeTimer = useRef<number | undefined>(undefined);

  const close = () => {
    window.clearTimeout(closeTimer.current);
    setSelected(null);
    setLive(null);
    setGoneAt(null);
    setFollow(false);
    sock.current?.inspect(null);
    scene.current?.setSelected(null);
  };

  const select = (id: number | null) => {
    if (id === null) return; // a click on empty space keeps the current selection
    window.clearTimeout(closeTimer.current);
    setSelected(id);
    setLive(null);
    setGoneAt(null);
    setFollow(false);
    scene.current?.setSelected(id);
    scene.current?.setFollow(false);
    sock.current?.inspect(id);
  };

  const onVehicle = (m: VehicleMsg) => {
    if (m.gone) {
      setGoneAt({ t: m.t_exit, laneChanges: m.lane_changes });
      setLive(null);
      scene.current?.setSelected(null);
      window.clearTimeout(closeTimer.current);
      closeTimer.current = window.setTimeout(close, GONE_CLOSE_MS);
      return;
    }
    const now = performance.now();
    if (now - lastShown.current >= READOUT_PERIOD_MS) {
      lastShown.current = now;
      setLive(m);
    }
  };

  const pick = useEffectEvent(select);
  const vehicle = useEffectEvent(onVehicle);
  const esc = useEffectEvent((e: KeyboardEvent) => {
    if (e.key === 'Escape' && selected !== null) close();
  });

  useEffect(() => {
    const s = sock.current;
    const sc = scene.current;
    if (!s || !sc) return;
    sc.setPickHandler((id) => pick(id));
    const off = s.on('vehicle', (m) => vehicle(m));
    const onKey = (e: KeyboardEvent) => esc(e);
    window.addEventListener('keydown', onKey);
    return () => {
      off();
      sc.setPickHandler(null);
      sc.setSelected(null);
      window.removeEventListener('keydown', onKey);
      window.clearTimeout(closeTimer.current);
    };
  }, [sock, scene]);

  if (selected === null) return null;
  return (
    <Inspector
      v={live}
      goneAt={goneAt}
      follow={follow}
      onFollow={() => {
        scene.current?.setFollow(!follow);
        setFollow(!follow);
      }}
      onClose={close}
    />
  );
}
