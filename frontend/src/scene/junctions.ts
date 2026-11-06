/** Junction plates, stop / give-way lines and turning-movement guides. */
import * as THREE from 'three';
import type { LaneData, NetworkData } from '../api/types';
import { simToThree, writeSimPoint, type Vec3 } from './coords';
import { LIFT, type Materials } from './materials';
import { mergeArrays, meshFrom } from './meshUtil';
import { dashes, offsetLeft, pointAt, polylineLength, ribbonArrays, type MeshArrays } from './ribbon';

function plateArrays(poly: Vec3[]): MeshArrays {
  const positions = new Float32Array(poly.length * 3);
  poly.forEach((p, i) => writeSimPoint(positions, i, p, LIFT.plate));
  const idx: number[] = [];
  for (let i = 1; i < poly.length - 1; i++) idx.push(0, i, i + 1); // CCW fan seen from above: faces up
  return { positions, indices: new Uint32Array(idx) };
}

/** Line across a lane at arc length s (from kerb edge to median edge). */
function across(lane: LaneData, s: number, inset = 0.1): Vec3[] {
  const l = offsetLeft(lane.centreline, lane.width_m / 2 - inset);
  const r = offsetLeft(lane.centreline, -(lane.width_m / 2 - inset));
  return [pointAt(l, s), pointAt(r, s)];
}

function stopLine(lane: LaneData, out: MeshArrays[]) {
  const len = polylineLength(lane.centreline);
  out.push(ribbonArrays(across(lane, len - 0.25), 0.3, LIFT.marking));
}

function giveWayMarking(lane: LaneData, out: MeshArrays[]) {
  const len = polylineLength(lane.centreline);
  for (const d of dashes(across(lane, len - 0.25), 0.6, 0.3)) out.push(ribbonArrays(d, 0.3, LIFT.marking));
  // Triangle on the approach, apex pointing at oncoming drivers (upstream).
  const apex = pointAt(lane.centreline, len - 7.5);
  const half = across(lane, len - 3, lane.width_m / 2 - 0.75);
  const tri = new Float32Array(9);
  writeSimPoint(tri, 0, half[0]!, LIFT.marking);
  writeSimPoint(tri, 1, half[1]!, LIFT.marking);
  writeSimPoint(tri, 2, apex, LIFT.marking);
  // One up-facing triangle (CCW seen from above). Adding both windings made the shared
  // vertex normals cancel, which rendered the marking black.
  out.push({ positions: tri, indices: new Uint32Array([0, 2, 1]) });
}

export function buildJunctions(net: NetworkData, mats: Materials): THREE.Group {
  const g = new THREE.Group();
  g.name = 'junctions';
  const lanes = new Map<string, LaneData>();
  for (const r of net.roads) for (const ln of r.lanes) lanes.set(ln.id, ln);

  g.add(meshFrom(mergeArrays(net.junctions.map((j) => plateArrays(j.polygon))), mats.junction, 'plates'));

  const lines: MeshArrays[] = [];
  for (const j of net.junctions) {
    const minor = new Set(j.minor_approach_lanes);
    for (const id of j.approach_lanes) {
      const lane = lanes.get(id);
      if (!lane) continue;
      if (j.control === 'signalised') stopLine(lane, lines);
      else if (minor.has(id)) giveWayMarking(lane, lines);
    }
  }
  if (lines.length) g.add(meshFrom(mergeArrays(lines), mats.white, 'stop-lines'));

  for (const c of net.connectors) {
    if (c.junction_id === null) continue;
    const pts = c.path.map((p) => new THREE.Vector3(...simToThree(p)).setY(p[2] + LIFT.guide));
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mats.guide[c.movement]);
    line.computeLineDistances();
    line.name = `guide:${c.id}`;
    g.add(line);
  }
  return g;
}
