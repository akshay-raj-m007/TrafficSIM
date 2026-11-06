import * as THREE from 'three';
import type { MeshArrays } from './ribbon';

/** Concatenate many triangle meshes into one (fewer draw calls). */
export function mergeArrays(parts: readonly MeshArrays[]): MeshArrays {
  let nv = 0;
  let ni = 0;
  for (const p of parts) {
    nv += p.positions.length;
    ni += p.indices.length;
  }
  const positions = new Float32Array(nv);
  const indices = new Uint32Array(ni);
  let vo = 0;
  let io = 0;
  for (const p of parts) {
    positions.set(p.positions, vo);
    const base = vo / 3;
    for (let i = 0; i < p.indices.length; i++) indices[io + i] = p.indices[i]! + base;
    vo += p.positions.length;
    io += p.indices.length;
  }
  return { positions, indices };
}

export function meshFrom(arrays: MeshArrays, material: THREE.Material, name = ''): THREE.Mesh {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(arrays.positions, 3));
  g.setIndex(new THREE.BufferAttribute(arrays.indices, 1));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, material);
  m.name = name;
  return m;
}

/** Free GPU buffers. Shared materials are kept unless `materials` is true. */
export function disposeTree(root: THREE.Object3D, materials = false): void {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    mesh.geometry?.dispose();
    if (!materials) return;
    const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
    else mat?.dispose();
  });
}
