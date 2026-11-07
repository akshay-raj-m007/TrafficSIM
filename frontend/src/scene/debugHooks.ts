/** Diagnostics for the headless-browser tests: rendered positions, draw counts, screen points. */
import type * as THREE from 'three';
import type { LaneFlowLayer } from './laneFlow';
import type { VehicleLayer } from './vehicles';

export interface DebugSources {
  camera: THREE.Camera;
  canvas: HTMLCanvasElement;
  vehicles: VehicleLayer;
  laneFlow: LaneFlowLayer;
  tick: () => number;
}

export function installDebug(d: DebugSources): void {
  (window as unknown as { __trafficDebug: unknown }).__trafficDebug = {
    probe: (n: number) => ({ tick: d.tick(), cars: d.vehicles.probe(n) }),
    drawn: () => [...d.vehicles.drawn],
    overflow: () => d.vehicles.overflow,
    screenPoints: (n: number) =>
      d.vehicles.screenPoints(d.camera, d.canvas.clientWidth, d.canvas.clientHeight, n),
    selectedOnScreen: () => {
      const p = d.vehicles.selectedPosition?.clone().project(d.camera);
      return p ? { x: p.x, y: p.y, visible: p.z < 1 } : null;
    },
    laneFlow: () => ({
      visible: d.laneFlow.group.visible,
      segments: d.laneFlow.segments,
      carrying: d.laneFlow.carrying,
    }),
  };
}
