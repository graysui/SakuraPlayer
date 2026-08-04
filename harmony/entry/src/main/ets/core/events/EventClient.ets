/**
 * WebSocket 事件客户端（realtime-events.md 契约）。
 *
 * - 握手携带 Bearer 访问令牌与 after_event_id 游标。
 * - close 4401/4403：refresh 后拉快照重连；4409/其他：直接拉快照重连。
 * - 每 30 秒发送 ping；连续两个周期无 pong 主动断开重连。
 * - 所有 on/off 回调为命名回调，可注销；页面/Ability 生命周期负责 stop()。
 */

import { webSocket } from '@kit.NetworkKit';
import { EventEnvelope, EventApplyResult } from './SnapshotStore';
import { SnapshotStore } from './SnapshotStore';
import { ApiClient } from '../api/ApiClient';

/** WebSocket 传输抽象（测试注入 Fake）。 */
export interface WebSocketTransport {
  connect(url: string, headers: Record<string, string>): Promise<void>;
  send(text: string): void;
  close(): void;
  setCallbacks(callbacks: WebSocketCallbacks): void;
}

export interface WebSocketCallbacks {
  onOpen: () => void;
  onMessage: (text: string) => void;
  onClose: (code: number) => void;
  onError: () => void;
}

/** 生产传输：Network Kit webSocket。 */
export class NetworkWebSocketTransport implements WebSocketTransport {
  private ws: webSocket.WebSocket | null = null;
  private callbacks: WebSocketCallbacks | null = null;

  setCallbacks(callbacks: WebSocketCallbacks): void {
    this.callbacks = callbacks;
  }

  connect(url: string, headers: Record<string, string>): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const ws = webSocket.createWebSocket();
      this.ws = ws;
      ws.on('open', () => {
        if (this.callbacks !== null) {
          this.callbacks.onOpen();
        }
        resolve();
      });
      ws.on('message', (err, data: string | ArrayBuffer) => {
        if (this.callbacks !== null) {
          this.callbacks.onMessage(typeof data === 'string' ? data : '');
        }
      });
      ws.on('close', (err, data) => {
        if (this.callbacks !== null) {
          this.callbacks.onClose(data.code);
        }
      });
      ws.on('error', (err) => {
        if (this.callbacks !== null) {
          this.callbacks.onError();
        }
        reject(new Error('websocket error'));
      });
      ws.connect(url, { header: headers });
    });
  }

  send(text: string): void {
    if (this.ws !== null) {
      try {
        this.ws.send(text);
      } catch (err) {
        // 心跳发送失败：等待超时机制触发重连
      }
    }
  }

  close(): void {
    if (this.ws !== null) {
      try {
        this.ws.close({ code: 1000, reason: 'client stop' });
      } catch (err) {
        // 已断开的连接忽略
      }
      this.ws = null;
    }
  }
}

/** 事件客户端：连接、去重投递、重连与心跳。 */
export class EventClient {
  private readonly transport: WebSocketTransport;
  private readonly apiClient: ApiClient;
  private readonly snapshot: SnapshotStore;
  private started: boolean = false;
  private connecting: boolean = false;
  private stopped: boolean = false;
  private pingTimer: number | null = null;
  private lastPongAt: number = 0;
  private missedPongCycles: number = 0;
  private reconnectDelayMs: number = 1000;
  private static readonly MAX_RECONNECT_DELAY_MS: number = 30000;

  constructor(transport: WebSocketTransport, apiClient: ApiClient, snapshot: SnapshotStore,
    reconnectDelayMs: number = 1000) {
    this.transport = transport;
    this.apiClient = apiClient;
    this.snapshot = snapshot;
    this.reconnectDelayMs = reconnectDelayMs;
    this.transport.setCallbacks({
      onOpen: (): void => this.onOpen(),
      onMessage: (text: string): void => this.onMessage(text),
      onClose: (code: number): void => this.onClose(code),
      onError: (): void => this.onError(),
    });
  }

  get isStarted(): boolean {
    return this.started;
  }

  /** 启动：先 REST 快照恢复，再无游标/带游标重连。 */
  async start(): Promise<void> {
    if (this.started) {
      return;
    }
    this.started = true;
    this.stopped = false;
    await this.snapshot.recover();
    await this.connect();
  }

  /** 停止：断开并释放定时器；可再次 start。 */
  stop(): void {
    this.stopped = true;
    this.started = false;
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
    this.transport.close();
  }

  private async connect(): Promise<void> {
    if (this.stopped || this.connecting) {
      return;
    }
    this.connecting = true;
    const base = this.apiClient.base;
    const cursor = this.snapshot.cursor;
    const suffix = cursor !== null ? `?after_event_id=${cursor}` : '';
    const url = `${base}/events/ws${suffix}`;
    const token = this.apiClient.getAccessToken();
    const headers: Record<string, string> = {};
    if (token !== null) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    try {
      await this.transport.connect(url, headers);
      this.startPing();
    } catch (err) {
      this.scheduleReconnect();
    } finally {
      this.connecting = false;
    }
  }

  private onOpen(): void {
    // 连接成功：重置退避延迟
    this.reconnectDelayMs = 1000;
  }

  private onMessage(text: string): void {
    if (text.length === 0) {
      return;
    }
    // pong 心跳
    if (text.includes('"pong"')) {
      this.lastPongAt = Date.now();
      this.missedPongCycles = 0;
      return;
    }
    let envelope: EventEnvelope;
    try {
      envelope = EventEnvelope.fromText(text);
    } catch (err) {
      // 未知/畸形事件：触发快照刷新，不崩溃
      this.snapshot.recover().catch((_err: Error) => {
        // 恢复失败静默，等待下次事件或断线重连
      });
      return;
    }
    const result = this.snapshot.apply(envelope);
    if (result === EventApplyResult.RECOVERED) {
      this.snapshot.recover().catch((_err: Error) => {
        // 恢复失败静默，等待下次事件或断线重连
      });
    }
  }

  private onClose(code: number): void {
    if (this.stopped) {
      return;
    }
    if (code === 4401 || code === 4403) {
      // 未认证/令牌过期：refresh 后拉快照重连；refresh 失败也拉快照（旧游标下不空转）
      this.apiClient.refresh().then(() => {
        this.snapshot.recover().finally(() => this.scheduleReconnect());
      }).catch(() => {
        this.snapshot.recover().finally(() => this.scheduleReconnect());
      });
      return;
    }
    // 4409（游标过旧）与其他关闭：拉快照重置游标后重连
    this.snapshot.recover().finally(() => this.scheduleReconnect());
  }

  private onError(): void {
    if (this.stopped) {
      return;
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.stopped) {
      return;
    }
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
    const delay = this.reconnectDelayMs;
    this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, EventClient.MAX_RECONNECT_DELAY_MS);
    setTimeout(() => {
      this.connect();
    }, delay);
  }

  private startPing(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer);
    }
    this.lastPongAt = Date.now();
    this.missedPongCycles = 0;
    this.pingTimer = setInterval(() => {
      this.transport.send(JSON.stringify({ type: 'ping', sent_at: new Date().toISOString() }));
      this.missedPongCycles++;
      if (this.missedPongCycles >= 2) {
        // 连续两个周期无 pong：断开重连
        this.transport.close();
      }
    }, 30000);
  }
}
