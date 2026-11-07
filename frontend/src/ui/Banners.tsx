import type { BuildingMsg } from '../api/messageTypes';
import type { ConnStatus } from '../api/simSocket';
import { useWaking } from './useWaking';

interface Props {
  building: BuildingMsg | null;
  serverError: string | null;
  /** The server-busy message while the connection is in the busy state, else null. */
  busy: string | null;
  netError: string | null;
  /** Connection state: not connected for a few seconds means the free host is waking up. */
  status: ConnStatus;
}

/** Status banners over the 3D view (building a scenario, errors, server busy). */
export function Banners({ building, serverError, busy, netError, status }: Props) {
  const waking = useWaking(status);
  return (
    <>
      {waking && (
        <div className="banner banner--busy" role="status" data-testid="waking">
          Waking up the server: the free host sleeps after 15 minutes without visitors, and starting
          it takes about a minute. This page connects by itself.
        </div>
      )}
      {building && (
        <div className="banner banner--busy" role="status" data-testid="building">
          Building “{building.name}” ({building.reason})… other sessions keep running.
        </div>
      )}
      {serverError && (
        <div className="banner banner--error" role="alert">
          {serverError}
        </div>
      )}
      {busy !== null && (
        <div className="banner banner--busy" role="alert">
          {busy} Retrying automatically every 15 s.
        </div>
      )}
      {netError && (
        <div className="banner banner--error" role="alert">
          Could not load the network: {netError}
        </div>
      )}
    </>
  );
}
