/**
 * WebSocket client for one live simulation session.
 *
 * - Reconnects with exponential backoff (1 s → 15 s) after unexpected closes.
 * - "Server busy" (close 1013) is surfaced to the UI and retried every 15 s.
 * - Measures, client-side: frame rate (Hz) over a sliding window and ping RTT.
 * - Disconnects when the tab has been hidden for 60 s (frees the server slot and
 *   metered egress) and reconnects when it becomes visible again.
 */
import { parseServerMessage, wsUrl } from './protocol';
import type { HelloMsg, TickMsg } from './types';

export type ConnStatus = 'connecting' | 'open' | 'busy' | 'closed';

export interface SimSocketEvents {
  onStatus(status: ConnStatus, detail?: string): void;
  onHello(msg: HelloMsg): void;
  onTick(msg: TickMsg, rateHz: number): void;
  onRtt(ms: number): void;
}

const BUSY_RETRY_MS = 15000;
const HIDDEN_DISCONNECT_MS = 60000;
const PING_MS = 2000;

export class SimSocket {
  private ws: WebSocket | null = null;
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
    this.ws = ws;
    let busy = false;
    ws.onopen = () => {
      this.backoff = 1000;
      this.pingTimer = window.setInterval(() => this.ping(), PING_MS);
    };
    ws.onmessage = (e: MessageEvent<string>) => {
      const msg = parseServerMessage(e.data);
      if (!msg) return;
      if (msg.type === 'hello') {
        this.ev.onStatus('open');
        this.ev.onHello(msg);
      } else if (msg.type === 'tick') this.ev.onTick(msg, this.measureRate());
      else if (msg.type === 'pong') this.onPong(msg.id);
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

  send(msg: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  setSpeed(speed: number): void {
    this.send({ type: 'set_speed', speed });
  }

  reset(seed: number): void {
    this.send({ type: 'reset', seed });
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

  private measureRate(): number {
    const now = performance.now();
    this.frameTimes.push(now);
    while (this.frameTimes.length > 0 && now - this.frameTimes[0]! > 2000) this.frameTimes.shift();
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
