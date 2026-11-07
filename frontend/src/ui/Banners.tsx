import type { BuildingMsg } from '../api/messageTypes';

interface Props {
  building: BuildingMsg | null;
  serverError: string | null;
  /** The server-busy message while the connection is in the busy state, else null. */
  busy: string | null;
  netError: string | null;
}

/** Status banners over the 3D view (building a scenario, errors, server busy). */
export function Banners({ building, serverError, busy, netError }: Props) {
  return (
    <>
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
