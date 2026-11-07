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
const SELECT_COLOUR = 0xfacc15;
const SELECT_GROW = { length: 1.4, height: 1.5, width: 1.6 }; // highlight box vs the vehicle box

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
  /** Frame id of the vehicle being inspected (highlighted), or null. */
  selected: number | null = null;
  /** Rendered centre of the selected vehicle in Three.js axes, null if it is not drawn. */
  selectedPosition: THREE.Vector3 | null = null;
  private highlight: THREE.LineSegments;
  private sel16 = new Float32Array(16);

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
    this.highlight = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)),
      new THREE.LineBasicMaterial({ color: SELECT_COLOUR, depthTest: false }),
    );
    this.highlight.matrixAutoUpdate = false;
    this.highlight.frustumCulled = false;
    this.highlight.renderOrder = 5;
    this.highlight.visible = false;
    this.group.add(this.highlight);
  }

  /** Select the vehicle to highlight (frame id), or null; deselecting takes effect at once. */
  select(frameId: number | null): void {
    this.selected = frameId;
    if (frameId === null) {
      this.selectedPosition = null;
      this.highlight.visible = false;
    }
  }

  /** Frame id of the vehicle under the ray, or null. */
  pickId(raycaster: THREE.Raycaster): number | null {
    // the cached bounding sphere may date from an empty buffer: refresh it for this click
    this.meshes.forEach((m) => m.computeBoundingSphere());
    const hit = raycaster.intersectObjects(this.meshes, false)[0];
    if (!hit || hit.instanceId === undefined) return null;
    const c = this.meshes.indexOf(hit.object as THREE.InstancedMesh);
    return c < 0 ? null : this.ids[c]![hit.instanceId]!;
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
    this.selectedPosition = null;
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
      writeBoxMatrix(
        mesh.instanceMatrix.array as Float32Array,
        k,
        pos,
        h,
        p,
        { sx: 1, sy: 1, sz: 1 },
        { up: info.height_m / 2, fwd: 0 },
      );
      if (s.id[i] === this.selected) this.markSelected(pos, h, p, info);
      const [r, g, b] = speedColour(s.speed[i]!);
      this.tmp.setRGB(r, g, b, THREE.SRGBColorSpace);
      mesh.setColorAt(k, this.tmp);
      if (s.brake[i] && lamps < CAPACITY_PER_CLASS * 4) {
        writeBoxMatrix(
          lampArr,
          lamps++,
          pos,
          h,
          p,
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
    this.highlight.visible = this.selectedPosition !== null;
  }

  private markSelected(
    pos: { x: number; y: number; z: number },
    heading: number,
    pitch: number,
    c: VehicleClassInfo,
  ): void {
    const size = {
      sx: c.length_m * SELECT_GROW.length,
      sy: c.height_m * SELECT_GROW.height,
      sz: c.width_m * SELECT_GROW.width,
    };
    writeBoxMatrix(this.sel16, 0, pos, heading, pitch, size, { up: c.height_m / 2, fwd: 0 });
    this.highlight.matrix.fromArray(this.sel16);
    this.selectedPosition = new THREE.Vector3(this.sel16[12], this.sel16[13], this.sel16[14]);
  }

  /** Screen positions (px, relative to the canvas) of the first `limit` cars: browser tests. */
  screenPoints(camera: THREE.Camera, w: number, h: number, limit: number) {
    const out: { id: number; x: number; y: number }[] = [];
    const mesh = this.meshes[0];
    if (!mesh) return out;
    const a = mesh.instanceMatrix.array as Float32Array;
    const v = new THREE.Vector3();
    for (let k = 0; k < mesh.count && out.length < limit; k++) {
      v.set(a[k * 16 + 12]!, a[k * 16 + 13]! + 0.7, a[k * 16 + 14]!).project(camera);
      if (v.z < 1 && Math.abs(v.x) < 0.95 && Math.abs(v.y) < 0.95) {
        out.push({ id: this.ids[0]![k]!, x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h });
      }
    }
    return out;
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
      out.push({
        id: this.ids[0]![k]!,
        x: a[k * 16 + 12]!,
        y: -a[k * 16 + 14]!,
        z: a[k * 16 + 13]!,
      });
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
    this.highlight.geometry.dispose();
    (this.highlight.material as THREE.Material).dispose();
  }
}
