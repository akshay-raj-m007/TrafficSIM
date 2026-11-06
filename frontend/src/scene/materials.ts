import * as THREE from 'three';

/** Vertical lifts [m] to avoid z-fighting between coplanar layers. Real, tiny offsets. */
export const LIFT = { ground: -0.05, plate: 0.004, road: 0, marking: 0.02, guide: 0.04 };

export function createMaterials() {
  const std = (color: number, extra: THREE.MeshStandardMaterialParameters = {}) =>
    new THREE.MeshStandardMaterial({ color, roughness: 0.92, metalness: 0, ...extra });
  return {
    ground: std(0x10151b),
    asphalt: std(0x2b3038),
    asphaltNarrow: std(0x353a42),
    asphaltDeck: std(0x30353e),
    junction: std(0x262a31),
    concrete: std(0x8b8f96, { side: THREE.DoubleSide, roughness: 0.8 }),
    concreteDark: std(0x5e636b, { side: THREE.DoubleSide }),
    white: std(0xe8e8e8, { roughness: 0.6 }),
    yellow: std(0xe2b33c, { roughness: 0.6 }),
    guide: {
      left: new THREE.LineDashedMaterial({ color: 0x4fd1c5, dashSize: 1.5, gapSize: 1, transparent: true, opacity: 0.75 }),
      through: new THREE.LineDashedMaterial({ color: 0xcbd5e1, dashSize: 1.5, gapSize: 1, transparent: true, opacity: 0.55 }),
      right: new THREE.LineDashedMaterial({ color: 0xf6ad55, dashSize: 1.5, gapSize: 1, transparent: true, opacity: 0.75 }),
    },
  };
}

export type Materials = ReturnType<typeof createMaterials>;
