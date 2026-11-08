import type { RefObject } from 'react';
import type { SimSocket } from '../api/simSocket';
import type { HelloMsg } from '../api/types';
import type { SceneManager } from '../scene/sceneManager';
import { ChartsHost } from './charts/ChartsHost';
import { InspectorHost } from './InspectorHost';

interface Props {
  sock: RefObject<SimSocket | null>;
  hello: HelloMsg | null;
  scene: RefObject<SceneManager | null>;
}

/** The overlays that talk to the live session (results drawer, vehicle inspector). */
export function Hosts({ sock, hello, scene }: Props) {
  return (
    <>
      <ChartsHost sock={sock} hello={hello} />
      <InspectorHost sock={sock} hello={hello} scene={scene} />
    </>
  );
}
