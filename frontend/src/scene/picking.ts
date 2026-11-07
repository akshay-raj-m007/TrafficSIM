import * as THREE from 'three';

/** Pointer movement / press time under which a press-release is a click, not a camera drag. */
export const CLICK_MAX_PX = 4;
export const CLICK_MAX_MS = 400;

export interface Press {
  x: number;
  y: number;
  t: number;
}

/** True if a press followed by a release is a click (so orbiting the camera never picks). */
export function isClick(down: Press | null, up: Press): boolean {
  if (!down) return false;
  return Math.hypot(up.x - down.x, up.y - down.y) <= CLICK_MAX_PX && up.t - down.t <= CLICK_MAX_MS;
}

/** Normalised device coordinates of a client point inside `box`. */
export function toNdc(clientX: number, clientY: number, box: DOMRect): THREE.Vector2 {
  return new THREE.Vector2(
    ((clientX - box.left) / box.width) * 2 - 1,
    -((clientY - box.top) / box.height) * 2 + 1,
  );
}

/** Calls `pick(raycaster)` for every click on the canvas (a drag is the camera). */
export function attachPicking(
  el: HTMLElement,
  camera: THREE.Camera,
  pick: (raycaster: THREE.Raycaster) => void,
): void {
  const raycaster = new THREE.Raycaster();
  let down: Press | null = null;
  el.addEventListener(
    'pointerdown',
    (e) => (down = { x: e.clientX, y: e.clientY, t: e.timeStamp }),
  );
  el.addEventListener('pointerup', (e) => {
    const press = { x: e.clientX, y: e.clientY, t: e.timeStamp };
    const d = down;
    down = null;
    if (!isClick(d, press)) return;
    raycaster.setFromCamera(toNdc(e.clientX, e.clientY, el.getBoundingClientRect()), camera);
    pick(raycaster);
  });
}
