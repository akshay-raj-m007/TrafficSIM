import type { BuildingMsg } from '../api/messageTypes';
import type { ConnStatus } from '../api/simSocket';
import { useWaking } from './useWaking';

interface Props {
  building: BuildingMsg | null;
  serverError: string | null;
  netError: string | null;
  /** Connection state: not connected for a few seconds means the free host is waking up. */
  status: ConnStatus;
  /** The server's message of the current status (busy / idle). */
  detail?: string;
  onResume(): void;
}

/** Status banners over the 3D view (building a scenario, errors, server busy). */
export function Banners({ building, serverError, netError, status, detail, onResume }: Props) {
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
      {status === 'busy' && (
        <div className="banner banner--busy" role="alert" data-testid="busy">
          {detail} Retrying automatically every 15 s.
        </div>
      )}
      {status === 'idle' && (
        <div className="banner banner--busy" role="alert" data-testid="idle">
          {detail}{' '}
          <button type="button" onClick={onResume}>
            Resume
          </button>
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
