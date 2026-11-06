/**
 * Vehicles as InstancedMeshes: one per vehicle class (true length × width × height in
 * metres, from the server's class table), coloured by speed, plus one small mesh of
 * brake lamps (instances only for braking vehicles). Matrices are written straight into
 * the instance buffers each display frame from the interpolated render state.
 */
import * as THREE from 'three';
import type { VehicleClassInfo } from '../api/types';
import { writeBoxMatrix } from './instanceMatrix';
import type { RenderState } from './interpolator';
import { speedColour } from './speedColor';

const CAPACITY_PER_CLASS = 2500; // instances per class mesh (peak demo load is ~700 in total)
const LAMP = { length: 0.08, height: 0.14, widthShare: 0.78, heightShare: 0.55 }; // metres / shares
const LAMP_COLOUR = 0xff2a2a;

export class VehicleLayer {
  readonly group = new THREE.Group();
  private meshes: THREE.InstancedMesh[] = [];
  private lamps: THREE.InstancedMesh;
  private classes: VehicleClassInfo[] = [];
  private counts: number[] = [];
  private ids: Uint16Array[] = [];
  private tmp = new THREE.Color();
  /** Vehicles in the last frame that did not fit in an instance buffer (should stay 0). */
  overflow = 0;

  constructor() {
    this.group.name = 'vehicles';
    const lampGeom = new THREE.BoxGeometry(1, 1, 1);
    this.lamps = new THREE.InstancedMesh(
      lampGeom,
      new THREE.MeshBasicMaterial({ color: LAMP_COLOUR }),
      CAPACITY_PER_CLASS * 4,
    );
    this.lamps.count = 0;
    this.lamps.frustumCulled = false;
    this.group.add(this.lamps);
  }

  setClasses(classes: VehicleClassInfo[]): void {
    this.meshes.forEach((m) => {
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
      this.group.remove(m);
    });
    this.classes = classes;
    this.meshes = classes.map((c) => {
      const mesh = new THREE.InstancedMesh(
        new THREE.BoxGeometry(c.length_m, c.height_m, c.width_m),
        new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.05 }),
        CAPACITY_PER_CLASS,
      );
      mesh.instanceColor = new THREE.InstancedBufferAttribute(
        new Float32Array(CAPACITY_PER_CLASS * 3),
        3,
      );
      mesh.count = 0;
      mesh.frustumCulled = false; // instances span the whole network
      mesh.name = `vehicles:${c.name}`;
      this.group.add(mesh);
      return mesh;
    });
    this.counts = classes.map(() => 0);
    this.ids = classes.map(() => new Uint16Array(CAPACITY_PER_CLASS));
  }

  update(s: RenderState | null): void {
    if (!s || this.meshes.length === 0) return;
    this.counts.fill(0);
    let lamps = 0;
    this.overflow = 0;
    const lampArr = this.lamps.instanceMatrix.array as Float32Array;
    for (let i = 0; i < s.n; i++) {
      const c = s.cls[i]!;
      const mesh = this.meshes[c];
      const info = this.classes[c];
      if (!mesh || !info) continue;
      const k = this.counts[c]!;
      if (k >= CAPACITY_PER_CLASS) {
        this.overflow++;
        continue;
      }
      this.counts[c] = k + 1;
      this.ids[c]![k] = s.id[i]!;
      const pos = { x: s.x[i]!, y: s.y[i]!, z: s.z[i]! };
      const h = s.heading[i]!;
      const p = s.pitch[i]!;
      writeBoxMatrix(mesh.instanceMatrix.array as Float32Array, k, pos, h, p,
        { sx: 1, sy: 1, sz: 1 }, { up: info.height_m / 2, fwd: 0 });
      const [r, g, b] = speedColour(s.speed[i]!);
      this.tmp.setRGB(r, g, b, THREE.SRGBColorSpace);
      mesh.setColorAt(k, this.tmp);
      if (s.brake[i] && lamps < CAPACITY_PER_CLASS * 4) {
        writeBoxMatrix(
          lampArr, lamps++, pos, h, p,
          { sx: LAMP.length, sy: LAMP.height, sz: info.width_m * LAMP.widthShare },
          { up: info.height_m * LAMP.heightShare, fwd: -info.length_m / 2 },
        );
      }
    }
    this.meshes.forEach((m, c) => {
      m.count = this.counts[c]!;
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    });
    this.lamps.count = lamps;
    this.lamps.instanceMatrix.needsUpdate = true;
  }

  /** Per-class number of instances drawn in the last update (for tests/diagnostics). */
  get drawn(): readonly number[] {
    return this.counts;
  }

  /** Rendered (sim x, y, z) and id of the first `limit` car instances: smoothness probes. */
  probe(limit: number): { id: number; x: number; y: number; z: number }[] {
    const out: { id: number; x: number; y: number; z: number }[] = [];
    const mesh = this.meshes[0];
    if (!mesh) return out;
    const a = mesh.instanceMatrix.array as Float32Array;
    for (let k = 0; k < Math.min(mesh.count, limit); k++) {
      out.push({ id: this.ids[0]![k]!, x: a[k * 16 + 12]!, y: -a[k * 16 + 14]!, z: a[k * 16 + 13]! });
    }
    return out;
  }

  dispose(): void {
    this.meshes.forEach((m) => {
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
    });
    this.lamps.geometry.dispose();
    (this.lamps.material as THREE.Material).dispose();
  }
}
