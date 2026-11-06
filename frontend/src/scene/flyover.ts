/**
 * Grade-separated structure: deck slab, ramp retaining walls, parapets and piers.
 * Dimensions come from the network meta (deck thickness) and road geometry; nothing
 * is scaled for looks.
 */
import * as THREE from 'three';
import type { NetworkData, RoadData } from '../api/types';
import { simToThree, type Vec3 } from './coords';
import type { Materials } from './materials';
import { mergeArrays, meshFrom } from './meshUtil';
import { offsetLeft, pointAt, polylineLength, stripArrays, type MeshArrays } from './ribbon';

const PARAPET_H = 1.0;
const PIER_SPACING = 30;
const PIER_RADIUS = 0.9;

function roadEdges(road: RoadData): { outer: Vec3[]; inner: Vec3[]; width: number } {
  const width = road.lanes.reduce((s, l) => s + l.width_m, 0);
  return {
    outer: offsetLeft(road.reference, road.inner_offset_m + width),
    inner: offsetLeft(road.reference, road.inner_offset_m),
    width,
  };
}

const withZ = (pts: Vec3[], z: (p: Vec3) => number): Vec3[] => pts.map((p) => [p[0], p[1], z(p)]);

function insideAnyJunction(net: NetworkData, p: Vec3, margin: number): boolean {
  return net.junctions.some((j) => {
    const xs = j.polygon.map((q) => q[0]);
    const ys = j.polygon.map((q) => q[1]);
    return (
      p[0] > Math.min(...xs) - margin &&
      p[0] < Math.max(...xs) + margin &&
      p[1] > Math.min(...ys) - margin &&
      p[1] < Math.max(...ys) + margin
    );
  });
}

export function buildFlyover(net: NetworkData, mats: Materials): THREE.Group {
  const t = net.meta.deck_thickness_m;
  const slab: MeshArrays[] = [];
  const walls: MeshArrays[] = [];
  const retaining: MeshArrays[] = [];
  const g = new THREE.Group();
  g.name = 'flyover';

  for (const road of net.roads.filter((r) => r.level > 0)) {
    const { outer, inner, width } = roadEdges(road);
    for (const edge of [outer, inner]) {
      // parapet on top of the running surface
      walls.push(stripArrays(withZ(edge, (p) => p[2] + PARAPET_H), edge));
      if (road.kind === 'ramp') retaining.push(stripArrays(edge, withZ(edge, () => 0))); // retaining wall
      else slab.push(stripArrays(edge, withZ(edge, (p) => p[2] - t))); // slab side face
    }
    if (road.kind !== 'flyover') continue;
    slab.push(stripArrays(withZ(outer, (p) => p[2] - t), withZ(inner, (p) => p[2] - t))); // soffit

    const mid = offsetLeft(road.reference, road.inner_offset_m + width / 2);
    const len = polylineLength(mid);
    for (let s = PIER_SPACING / 2; s < len; s += PIER_SPACING) {
      const p = pointAt(mid, s);
      if (insideAnyJunction(net, p, 3)) continue; // keep the junction below clear
      const h = p[2] - t;
      const column = new THREE.Mesh(new THREE.CylinderGeometry(PIER_RADIUS, PIER_RADIUS, h, 16), mats.concreteDark);
      const [x, , z] = simToThree(p);
      column.position.set(x, h / 2, z);
      const cap = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.8, width - 1), mats.concrete);
      cap.position.set(x, h - 0.4, z);
      const dir = pointAt(mid, Math.min(len, s + 1));
      cap.rotation.y = -Math.atan2(dir[1] - p[1], dir[0] - p[0]); // align with the road
      g.add(column, cap);
    }
  }
  g.add(meshFrom(mergeArrays(slab), mats.concrete, 'deck-slab'));
  g.add(meshFrom(mergeArrays(walls), mats.concrete, 'parapets'));
  g.add(meshFrom(mergeArrays(retaining), mats.concreteDark, 'ramp-walls'));
  return g;
}
