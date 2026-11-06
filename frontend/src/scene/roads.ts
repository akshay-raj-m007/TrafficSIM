/** Lane surfaces and lane markings, built from the backend's exact lane geometry. */
import * as THREE from 'three';
import type { NetworkData, RoadData } from '../api/types';
import type { Vec3 } from './coords';
import { LIFT, type Materials } from './materials';
import { mergeArrays, meshFrom } from './meshUtil';
import { dashes, offsetLeft, pointAt, polylineLength, ribbonArrays, type MeshArrays } from './ribbon';

const LINE_W = 0.12; // lane separator width [m]
const EDGE_W = 0.15; // edge line width [m]
const EDGE_INSET = 0.25; // edge line centre distance from the carriageway edge [m]
const DASH = 3.0; // dash length [m]
const GAP = 4.5; // gap length [m]
const TAPER = 100; // hatched length at the end of a dropped lane [m]

export function buildLanes(net: NetworkData, mats: Materials): THREE.Group {
  const normal: MeshArrays[] = [];
  const narrow: MeshArrays[] = [];
  const deck: MeshArrays[] = [];
  for (const road of net.roads) {
    for (const lane of road.lanes) {
      const arr = ribbonArrays(lane.centreline, lane.width_m, LIFT.road);
      if (road.level > 0) deck.push(arr);
      else if (lane.width_m < 3.5) narrow.push(arr);
      else normal.push(arr);
    }
  }
  const g = new THREE.Group();
  g.name = 'lanes';
  g.add(meshFrom(mergeArrays(normal), mats.asphalt, 'lanes-3.5m'));
  g.add(meshFrom(mergeArrays(narrow), mats.asphaltNarrow, 'lanes-narrow'));
  g.add(meshFrom(mergeArrays(deck), mats.asphaltDeck, 'lanes-deck'));
  return g;
}

/** Lanes that end without a successor on a road that is not a network exit. */
export function droppedLaneIds(net: NetworkData): Set<string> {
  const hasNext = new Set(net.connectors.map((c) => c.from_lane));
  const exits = new Set(net.zones.map((z) => z.exit_road));
  const out = new Set<string>();
  for (const r of net.roads) {
    if (exits.has(r.id)) continue;
    for (const ln of r.lanes) if (!hasNext.has(ln.id)) out.add(ln.id);
  }
  return out;
}

function roadMarkings(road: RoadData, medianHalf: number, white: MeshArrays[], yellow: MeshArrays[]) {
  const lanes = road.lanes;
  for (let k = 0; k < lanes.length - 1; k++) {
    const ln = lanes[k]!;
    const boundary = offsetLeft(ln.centreline, -ln.width_m / 2); // right side of lane k
    for (const d of dashes(boundary, DASH, GAP)) white.push(ribbonArrays(d, LINE_W, LIFT.marking));
  }
  const kerb = lanes[0]!;
  white.push(ribbonArrays(offsetLeft(kerb.centreline, kerb.width_m / 2 - EDGE_INSET), EDGE_W, LIFT.marking));
  const med = lanes[lanes.length - 1]!;
  const medEdge = offsetLeft(med.centreline, -(med.width_m / 2 - EDGE_INSET));
  const atMedian = road.inner_offset_m <= medianHalf + 1e-6;
  (atMedian ? yellow : white).push(ribbonArrays(medEdge, EDGE_W, LIFT.marking));
}

function dropHatch(centre: Vec3[], width: number, out: MeshArrays[]) {
  const len = polylineLength(centre);
  const left = offsetLeft(centre, width / 2 - 0.2);
  const right = offsetLeft(centre, -(width / 2 - 0.2));
  for (let s = Math.max(0, len - TAPER); s < len - 3; s += 5) {
    // diagonal chevron stripe across the lane, 0.3 m wide
    const a = pointAt(left, s);
    const b = pointAt(right, s + 3);
    const stripe: Vec3[] = [a, b];
    out.push(ribbonArrays(stripe, 0.3, LIFT.marking));
  }
}

export function buildMarkings(net: NetworkData, mats: Materials): THREE.Group {
  const white: MeshArrays[] = [];
  const yellow: MeshArrays[] = [];
  for (const road of net.roads) roadMarkings(road, net.meta.median_half_m, white, yellow);
  const dropped = droppedLaneIds(net);
  for (const road of net.roads) {
    for (const ln of road.lanes) if (dropped.has(ln.id)) dropHatch(ln.centreline, ln.width_m, white);
  }
  const g = new THREE.Group();
  g.name = 'markings';
  g.add(meshFrom(mergeArrays(white), mats.white, 'markings-white'));
  if (yellow.length) g.add(meshFrom(mergeArrays(yellow), mats.yellow, 'markings-yellow'));
  return g;
}

