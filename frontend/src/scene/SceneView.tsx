import { useEffect, useRef, type MutableRefObject } from 'react';
import type { NetworkData, VehicleClassInfo } from '../api/types';
import { Legend } from '../ui/Legend';
import { SceneManager, VIEWS, type ViewName } from './sceneManager';

interface Props {
  network: NetworkData | null;
  classes: VehicleClassInfo[];
  /** Lets the app push frames into the scene without going through React state. */
  managerRef: MutableRefObject<SceneManager | null>;
}

export function SceneView({ network, classes, managerRef }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mgrRef = managerRef;

  useEffect(() => {
    const mgr = new SceneManager(hostRef.current!);
    mgrRef.current = mgr;
    return () => {
      mgr.dispose();
      mgrRef.current = null;
    };
  }, [mgrRef]);

  useEffect(() => {
    if (network) mgrRef.current?.setNetwork(network);
  }, [network, mgrRef]);

  return (
    <div className="viewport">
      <div ref={hostRef} className="viewport__canvas" />
      <div className="viewport__views">
        {(Object.keys(VIEWS) as ViewName[]).map((v) => (
          <button key={v} type="button" onClick={() => mgrRef.current?.view(v)}>
            {v}
          </button>
        ))}
      </div>
      <Legend classes={classes} />
    </div>
  );
}
