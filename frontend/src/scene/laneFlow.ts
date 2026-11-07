/**
 * "Lane flow" overlay: one thin ribbon per lane and junction connector, coloured by the
 * measured flow of that segment (kpi message `lane_flow`, last 5 min, indexed like the frame segments).
 * All ribbons are one merged mesh with vertex colours, so recolouring at 1 Hz is one buffer
 * write and drawing costs one draw call. Hidden by default.
 */
import * as THREE from 'three';
import type { NetworkData, SegmentInfo } from '../api/types';
import type { Vec3 } from './coords';
import { FLOW_UNUSED_VEH_H, flowColour } from './flowColor';
import { LIFT } from './materials';
import { mergeArrays } from './meshUtil';
import { ribbonArrays, type MeshArrays } from './ribbon';

const OVERLAY_LIFT_M = LIFT.guide + 0.02; // above the markings and the guide lines
const OVERLAY_OPACITY = 0.8;
/** Connector ribbons are as wide as the lane they start from. */
const FALLBACK_WIDTH_M = 3.0;

export class LaneFlowLayer {
  readonly group = new THREE.Group();
  private colours: THREE.BufferAttribute | null = null;
  private vertexStart: number[] = [];
  private vertexCount: number[] = [];
  private last: readonly number[] | null = null;

  constructor() {
    this.group.name = 'lane-flow';
    this.group.visible = false;
  }

  get segments(): number {
    return this.vertexStart.length;
  }

  /** Segments currently painted as carrying traffic (diagnostics for the browser tests). */
  get carrying(): number {
    return this.last?.filter((v) => v >= FLOW_UNUSED_VEH_H).length ?? 0;
  }

  /** (Re)build the ribbons for this network and segment table. */
  build(net: NetworkData, segments: readonly SegmentInfo[]): void {
    this.clear();
    const width = new Map<string, number>();
    const line = new Map<string, Vec3[]>();
    for (const r of net.roads) {
      for (const l of r.lanes) {
        width.set(l.id, l.width_m);
        line.set(l.id, l.centreline);
      }
    }
    for (const c of net.connectors) {
      width.set(c.id, width.get(c.from_lane) ?? FALLBACK_WIDTH_M);
      line.set(c.id, c.path);
    }
    const parts: MeshArrays[] = [];
    let start = 0;
    for (const s of segments) {
      const pts = line.get(s.id);
      if (!pts) throw new Error(`segment ${s.id} is not in the network geometry`);
      const arr = ribbonArrays(pts, width.get(s.id)!, OVERLAY_LIFT_M);
      parts.push(arr);
      const n = arr.positions.length / 3;
      this.vertexStart.push(start);
      this.vertexCount.push(n);
      start += n;
    }
    const merged = mergeArrays(parts);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(merged.positions, 3));
    g.setIndex(new THREE.BufferAttribute(merged.indices, 1));
    this.colours = new THREE.BufferAttribute(new Float32Array(merged.positions.length), 3);
    g.setAttribute('color', this.colours);
    const mat = new THREE.MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: OVERLAY_OPACITY,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(g, mat);
    mesh.name = 'lane-flow-mesh';
    mesh.renderOrder = 2;
    this.group.add(mesh);
    this.paint(this.last ?? new Array<number>(segments.length).fill(0));
  }

  /** Colour every segment from `flows` (veh/h per segment index). */
  paint(flows: readonly number[]): void {
    this.last = flows;
    const attr = this.colours;
    if (!attr || flows.length !== this.vertexStart.length) return;
    const a = attr.array as Float32Array;
    for (let k = 0; k < flows.length; k++) {
      const [r, g, b] = flowColour(flows[k]!);
      const o = this.vertexStart[k]! * 3;
      for (let v = 0; v < this.vertexCount[k]!; v++) {
        a[o + 3 * v] = r;
        a[o + 3 * v + 1] = g;
        a[o + 3 * v + 2] = b;
      }
    }
    attr.needsUpdate = true;
  }

  setVisible(on: boolean): void {
    this.group.visible = on;
  }

  private clear(): void {
    for (const c of [...this.group.children]) {
      const m = c as THREE.Mesh;
      m.geometry?.dispose();
      (m.material as THREE.Material | undefined)?.dispose();
      this.group.remove(c);
    }
    this.vertexStart = [];
    this.vertexCount = [];
    this.colours = null;
  }

  dispose(): void {
    this.clear();
  }
}
