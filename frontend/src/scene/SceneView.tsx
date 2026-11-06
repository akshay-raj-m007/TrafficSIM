import { useEffect, useRef } from 'react';
import type { NetworkData } from '../api/types';
import { SceneManager, VIEWS, type ViewName } from './sceneManager';

interface Props {
  network: NetworkData | null;
}

export function SceneView({ network }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mgrRef = useRef<SceneManager | null>(null);

  useEffect(() => {
    const mgr = new SceneManager(hostRef.current!);
    mgrRef.current = mgr;
    return () => {
      mgr.dispose();
      mgrRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (network) mgrRef.current?.setNetwork(network);
  }, [network]);

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
      <div className="viewport__legend">
        <span className="dot dot--left" /> left turn
        <span className="dot dot--through" /> through
        <span className="dot dot--right" /> right turn
        <span className="legend__note">1 unit = 1 m · left-hand traffic · grid 100 m</span>
      </div>
    </div>
  );
}
