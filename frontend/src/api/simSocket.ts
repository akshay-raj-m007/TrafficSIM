/**
 * WebSocket client for one live simulation session.
 *
 * - Binary messages are vehicle frames (decoded with the format from `hello`); text
 *   messages are JSON (hello, kpi, stats, busy, pong, error).
 * - Reconnects with exponential backoff (1 s → 15 s) after unexpected closes.
 * - "Server busy" (close 1013) is surfaced to the UI and retried every 15 s.
 * - Measures, client-side: frame rate (Hz) over a sliding window and ping RTT.
 * - Disconnects when the tab has been hidden for 60 s (frees the server slot and
 *   metered egress) and reconnects when it becomes visible again.
 */
import { decodeFrame, type Frame } from './frame';
import { parseServerMessage, wsUrl } from './protocol';
import type { LiveChange, ScenarioDoc } from './scenarioTypes';
import type { AppliedMsg, BuildingMsg, ErrorMsg, RejectedMsg, ScenarioMsg } from './messageTypes';
import type { FrameFormat, HelloMsg, KpiMsg, StatsMsg } from './types';

export type ConnStatus = 'connecting' | 'open' | 'busy' | 'closed';

export interface SimSocketEvents {
  onStatus(status: ConnStatus, detail?: string): void;
  onHello(msg: HelloMsg): void;
  onFrame(frame: Frame, nowMs: number, rateHz: number): void;
  onKpi(msg: KpiMsg): void;
  onStats(msg: StatsMsg): void;
  onRtt(ms: number): void;
  onApplied(msg: AppliedMsg): void;
  onRejected(msg: RejectedMsg): void;
  onScenario(msg: ScenarioMsg): void;
  onBuilding(msg: BuildingMsg): void;
  onError(msg: ErrorMsg): void;
}

const BUSY_RETRY_MS = 15000;
const HIDDEN_DISCONNECT_MS = 60000;
const PING_MS = 2000;
const RATE_WINDOW_MS = 2000;

export class SimSocket {
  private ws: WebSocket | null = null;
  private fmt: FrameFormat | null = null;
  private backoff = 1000;
  private retryTimer: number | undefined;
  private pingTimer: number | undefined;
  private hiddenTimer: number | undefined;
  private pingId = 0;
  private pingSent = new Map<number, number>();
  private frameTimes: number[] = [];
  private stopped = false;

  constructor(private readonly ev: SimSocketEvents) {
    document.addEventListener('visibilitychange', this.onVisibility);
  }

  connect(): void {
    this.stopped = false;
    window.clearTimeout(this.retryTimer);
    this.ev.onStatus('connecting');
    const ws = new WebSocket(wsUrl('/ws/sim', window.location));
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    let busy = false;
    ws.onopen = () => {
      this.backoff = 1000;
      this.pingTimer = window.setInterval(() => this.ping(), PING_MS);
    };
    ws.onmessage = (e: MessageEvent<string | ArrayBuffer>) => {
      if (typeof e.data !== 'string') {
        if (this.fmt) this.onBinary(e.data);
        return;
      }
      const msg = parseServerMessage(e.data);
      if (!msg) return;
      if (msg.type === 'hello') {
        this.fmt = msg.frame;
        this.ev.onStatus('open');
        this.ev.onHello(msg);
      } else if (msg.type === 'kpi') this.ev.onKpi(msg);
      else if (msg.type === 'stats') this.ev.onStats(msg);
      else if (msg.type === 'pong') this.onPong(msg.id);
      else if (msg.type === 'applied') this.ev.onApplied(msg);
      else if (msg.type === 'rejected') this.ev.onRejected(msg);
      else if (msg.type === 'scenario') this.ev.onScenario(msg);
      else if (msg.type === 'building') this.ev.onBuilding(msg);
      else if (msg.type === 'error') this.ev.onError(msg);
      else if (msg.type === 'busy') {
        busy = true;
        this.ev.onStatus('busy', msg.message);
      }
    };
    ws.onclose = (e) => {
      window.clearInterval(this.pingTimer);
      this.ws = null;
      if (this.stopped) return;
      if (busy || e.code === 1013) {
        this.retryTimer = window.setTimeout(() => this.connect(), BUSY_RETRY_MS);
        return;
      }
      this.ev.onStatus('closed', `connection lost (code ${e.code}); retrying`);
      this.retryTimer = window.setTimeout(() => this.connect(), this.backoff);
      this.backoff = Math.min(this.backoff * 2, 15000);
    };
  }

  private onBinary(buf: ArrayBuffer): void {
    try {
      const now = performance.now();
      this.ev.onFrame(decodeFrame(buf, this.fmt!), now, this.measureRate(now));
    } catch {
      /* a malformed frame is dropped; the next one resynchronises */
    }
  }

  send(msg: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  setSpeed(speed: number): void {
    this.send({ type: 'set_speed', speed });
  }

  reset(seed: number): void {
    this.send({ type: 'reset', seed });
  }

  /** Reset to a named preset (optionally with a seed) or to a whole scenario document. */
  resetTo(target: { preset: string; seed?: number } | { scenario: ScenarioDoc }): void {
    this.send({ type: 'reset', ...target });
  }

  applyChange(change: LiveChange): void {
    this.send({ type: 'apply', change });
  }

  exportScenario(): void {
    this.send({ type: 'export' });
  }

  close(): void {
    this.stopped = true;
    window.clearTimeout(this.retryTimer);
    window.clearInterval(this.pingTimer);
    this.ws?.close();
    this.ev.onStatus('closed', 'disconnected');
  }

  dispose(): void {
    document.removeEventListener('visibilitychange', this.onVisibility);
    window.clearTimeout(this.hiddenTimer);
    this.close();
  }

  private ping(): void {
    const id = ++this.pingId;
    this.pingSent.set(id, performance.now());
    this.send({ type: 'ping', id });
  }

  private onPong(id: number): void {
    const t0 = this.pingSent.get(id);
    this.pingSent.delete(id);
    if (t0 !== undefined) this.ev.onRtt(performance.now() - t0);
  }

  private measureRate(now: number): number {
    this.frameTimes.push(now);
    while (this.frameTimes.length > 0 && now - this.frameTimes[0]! > RATE_WINDOW_MS) {
      this.frameTimes.shift();
    }
    const n = this.frameTimes.length;
    return n > 1 ? ((n - 1) * 1000) / (now - this.frameTimes[0]!) : 0;
  }

  private onVisibility = (): void => {
    if (document.hidden) {
      this.hiddenTimer = window.setTimeout(() => this.close(), HIDDEN_DISCONNECT_MS);
    } else {
      window.clearTimeout(this.hiddenTimer);
      if (this.stopped) this.connect();
    }
  };
}
