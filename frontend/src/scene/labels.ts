/** Screen-space labels (from backend annotations) and a 10 m ground scale bar. */
import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import type { NetworkData } from '../api/types';
import { simToThree, type Vec3 } from './coords';
import { LIFT, type Materials } from './materials';
import { mergeArrays, meshFrom } from './meshUtil';
import { ribbonArrays, type MeshArrays } from './ribbon';

function label(text: string, cls = 'scene-label'): CSS2DObject {
  const el = document.createElement('div');
  el.className = cls;
  el.textContent = text;
  return new CSS2DObject(el);
}

export function buildLabels(net: NetworkData): THREE.Group {
  const g = new THREE.Group();
  g.name = 'labels';
  for (const a of net.annotations) {
    const obj = label(a.text);
    const [x, y, z] = simToThree(a.position);
    obj.position.set(x, y + 2, z);
    g.add(obj);
  }
  return g;
}

/** Ten alternating 1 m blocks on the ground: a direct visual check of the metre scale. */
export function buildScaleBar(mats: Materials, origin: Vec3 = [-70, -40, 0]): THREE.Group {
  const light: MeshArrays[] = [];
  const dark: MeshArrays[] = [];
  for (let i = 0; i < 10; i++) {
    const seg: Vec3[] = [
      [origin[0] + i, origin[1], origin[2]],
      [origin[0] + i + 1, origin[1], origin[2]],
    ];
    (i % 2 === 0 ? light : dark).push(ribbonArrays(seg, 0.5, LIFT.marking));
  }
  const g = new THREE.Group();
  g.name = 'scale-bar';
  g.add(meshFrom(mergeArrays(light), mats.white, 'scale-light'));
  g.add(meshFrom(mergeArrays(dark), mats.yellow, 'scale-dark'));
  const tag = label('10 m', 'scene-label scene-label--scale');
  const [x, y, z] = simToThree([origin[0] + 5, origin[1] - 1.5, origin[2]]);
  tag.position.set(x, y + 0.5, z);
  g.add(tag);
  return g;
}
