import { useEffect, useState } from 'react';
import type { ConnStatus } from '../api/simSocket';

/** Not connected for this long: the (free) host is probably asleep and starting up. */
export const WAKE_AFTER_MS = 4000;

/** True while the socket has been connecting or retrying for WAKE_AFTER_MS. */
export function useWaking(status: ConnStatus): boolean {
  const [waking, setWaking] = useState(false);
  const down = status === 'connecting' || status === 'closed';
  useEffect(() => {
    if (!down) {
      const t = window.setTimeout(() => setWaking(false), 0);
      return () => window.clearTimeout(t);
    }
    const t = window.setTimeout(() => setWaking(true), WAKE_AFTER_MS);
    return () => window.clearTimeout(t);
  }, [down]);
  return waking && down;
}
