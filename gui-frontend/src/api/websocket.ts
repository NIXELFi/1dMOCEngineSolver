import type { ServerMessage } from "../types/events";

type Listener = (msg: ServerMessage) => void;

const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 10000];

export class EventSocket {
  private ws: WebSocket | null = null;
  private listeners: Set<Listener> = new Set();
  private reconnectAttempt = 0;
  private heartbeatTimer: number | null = null;
  private closed = false;

  constructor(private url: string) {}

  connect() {
    this.closed = false;
    this._open();
  }

  private _open() {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      this._startHeartbeat();
    };
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as ServerMessage;
        this.listeners.forEach((l) => l(msg));
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };
    this.ws.onclose = () => {
      this._stopHeartbeat();
      if (!this.closed) {
        this._scheduleReconnect();
      }
    };
    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private _scheduleReconnect() {
    const delay =
      RECONNECT_DELAYS_MS[
        Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)
      ];
    this.reconnectAttempt += 1;
    setTimeout(() => {
      if (!this.closed) this._open();
    }, delay);
  }

  private _startHeartbeat() {
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  }

  private _stopHeartbeat() {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  addListener(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  close() {
    this.closed = true;
    this._stopHeartbeat();
    this.ws?.close();
  }
}

export function makeEventSocket(): EventSocket {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${window.location.host}/ws/events`;
  return new EventSocket(url);
}
