/**
 * Owns the Three.js renderer, camera and render loop, outside React's render cycle.
 * Rendering runs at display rate; simulation state (step 2) arrives at 10 Hz and will be
 * interpolated here between the two most recent sim frames.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';
import type { NetworkData } from '../api/types';
import { simToThree, type Vec3 } from './coords';
import { buildFlyover } from './flyover';
import { buildJunctions } from './junctions';
import { buildLabels, buildScaleBar } from './labels';
import { createMaterials, LIFT } from './materials';
import { disposeTree } from './meshUtil';
import { buildLanes, buildMarkings } from './roads';

/** Camera presets: [target, camera position], both in SIM coordinates (metres). */
export const VIEWS = {
  overview: { target: [200, 0, 0], eye: [-200, -760, 360] },
  J1: { target: [0, 0, 0], eye: [-70, -110, 70] },
  flyover: { target: [-300, 0, 3], eye: [-420, -150, 75] },
  'lane drop': { target: [860, 0, 0], eye: [760, -90, 55] },
  J2: { target: [1100, 0, 0], eye: [1040, -80, 55] },
} satisfies Record<string, { target: Vec3; eye: Vec3 }>;
export type ViewName = keyof typeof VIEWS;

export class SceneManager {
  private renderer: THREE.WebGLRenderer;
  private labels: CSS2DRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private mats = createMaterials();
  private networkRoot = new THREE.Group();
  private raf = 0;
  private resizeObs: ResizeObserver;

  constructor(private container: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);
    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = 'label-layer';
    container.appendChild(this.labels.domElement);

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.5, 12000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI * 0.495; // stay above ground

    this.scene.background = new THREE.Color(0x0b0f14);
    this.scene.fog = new THREE.Fog(0x0b0f14, 2500, 7000);
    this.scene.add(new THREE.HemisphereLight(0xc8d8ff, 0x1a1a1a, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.8);
    sun.position.set(-600, 900, 500);
    this.scene.add(sun, this.networkRoot, ...this.groundAndGrid());

    this.view('overview');
    this.resizeObs = new ResizeObserver(() => this.resize());
    this.resizeObs.observe(container);
    this.resize();
    this.loop();
  }

  private groundAndGrid(): THREE.Object3D[] {
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(6000, 3000), this.mats.ground);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(250, LIFT.ground, 0);
    const grid = new THREE.GridHelper(6000, 60, 0x2a3440, 0x18202a); // 100 m cells
    grid.position.set(250, LIFT.ground + 0.01, 0);
    return [ground, grid];
  }

  setNetwork(net: NetworkData): void {
    disposeTree(this.networkRoot);
    this.networkRoot.clear();
    this.networkRoot.add(
      buildLanes(net, this.mats),
      buildMarkings(net, this.mats),
      buildJunctions(net, this.mats),
      buildFlyover(net, this.mats),
      buildLabels(net),
      buildScaleBar(this.mats),
    );
  }

  view(name: ViewName): void {
    const v = VIEWS[name];
    this.controls.target.set(...simToThree(v.target));
    this.camera.position.set(...simToThree(v.eye));
    this.controls.update();
  }

  private resize(): void {
    const w = Math.max(1, this.container.clientWidth);
    const h = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(w, h);
    this.labels.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private loop = (): void => {
    this.raf = requestAnimationFrame(this.loop);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  };

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.resizeObs.disconnect();
    this.controls.dispose();
    disposeTree(this.scene, true);
    Object.values(this.mats.guide).forEach((m) => m.dispose());
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labels.domElement.remove();
  }
}
