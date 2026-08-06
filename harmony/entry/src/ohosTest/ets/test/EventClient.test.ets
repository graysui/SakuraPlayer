/**
 * TASK-302 事件合并与连接生命周期测试。
 *
 * 验证 realtime-events 契约：event_id 去重、sequence 跳号恢复、
 * stream_version 浅合并、4409/4401 关闭恢复重连、未知类型不崩溃、stop 可注销。
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { TokenPair } from '../../../main/ets/core/api/ApiModels';
import { SecureSessionStore, SecretStore } from '../../../main/ets/core/auth/SecureSessionStore';
import { EventApplyResult, EventEnvelope, SnapshotStore } from '../../../main/ets/core/events/SnapshotStore';
import { EventClient, WebSocketCallbacks, WebSocketTransport } from '../../../main/ets/core/events/EventClient';

class FakeSecretStore implements SecretStore {
  private store: Map<string, string> = new Map();

  async write(alias: string, secret: string): Promise<void> {
    this.store.set(alias, secret);
  }

  async read(alias: string): Promise<string | null> {
    const value = this.store.get(alias);
    return value === undefined ? null : value;
  }

  async remove(alias: string): Promise<void> {
    this.store.delete(alias);
  }
}

class QueuedResponse {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    this.status = status;
    this.body = body;
  }
}

class FakeHttpTransport implements HttpTransport {
  responses: QueuedResponse[] = [];

  async request(_request: HttpRequest): Promise<HttpResponse> {
    const next = this.responses.shift();
    if (next === undefined) {
      throw new Error('no queued response');
    }
    return { statusCode: next.status, body: next.body };
  }

  static snapshotBody(version: number, lastEventId: string | null): string {
    const cursor = lastEventId === null ? 'null' : `"${lastEventId}"`;
    return `{"snapshot_version":${version},"last_event_id":${cursor},` +
      `"queues":{"metadata_queued":0,"metadata_running":0,"metadata_paused":false,` +
      `"cache_queued":0,"cache_running":0,"cache_ready":0},` +
      `"cache_jobs":[{"id":"j1","movie_id":"m1","source_id":"s1","status":"queued",` +
      `"remote_percent":null,"error_code":null,"media_candidates":[],` +
      `"selected_media_ids":[],"subtitles":[],"created_at":"2026-08-04T00:00:00Z",` +
      `"updated_at":"2026-08-04T00:00:00Z"}],` +
      `"metadata_jobs":[],"cloud115_binding":{"bound":false,"status":"unbound","display_name":null,"cache_root_ready":false,"last_verified_at":null},"notifications":[]}`;
  }
}

class FakeWebSocketTransport implements WebSocketTransport {
  callbacks: WebSocketCallbacks | null = null;
  connectUrls: string[] = [];
  closed: boolean = false;

  setCallbacks(callbacks: WebSocketCallbacks): void {
    this.callbacks = callbacks;
  }

  async connect(url: string, _headers: Record<string, string>): Promise<void> {
    this.connectUrls.push(url);
  }

  send(_text: string): void {
  }

  close(): void {
    this.closed = true;
  }

  emitMessage(text: string): void {
    if (this.callbacks !== null) {
      this.callbacks.onMessage(text);
    }
  }

  emitClose(code: number): void {
    if (this.callbacks !== null) {
      this.callbacks.onClose(code);
    }
  }
}

function envelope(sequence: number, streamVersion: number, type: string, resource: string): EventEnvelope {
  const resourceJson = resource.length > 0 ? `,"resource":${resource}` : '';
  const body = `{"version":1,"event_id":"evt-${sequence}","sequence":${sequence},` +
    `"stream":"${type.startsWith('cache') ? 'cache' : 'notification'}",` +
    `"stream_version":${streamVersion},"type":"${type}",` +
    `"occurred_at":"2026-08-04T00:00:00Z"${resourceJson}}`;
  return EventEnvelope.fromText(body);
}

export default function eventClientTest() {
  describe('SnapshotStoreTest', () => {
    it('duplicate_event_id_ignored', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(5, 'cursor-5')));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      const store = new SnapshotStore(client);
      await store.recover();

      const event = envelope(6, 1, 'cache.job.updated.v1', '{"id":"j1","status":"offlining"}');
      expect(store.apply(event)).assertEqual(EventApplyResult.APPLIED);
      expect(store.apply(event)).assertEqual(EventApplyResult.IGNORED);
      done();
    });

    it('sequence_gap_triggers_recover', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(5, 'cursor-5')));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      const store = new SnapshotStore(client);
      await store.recover();

      // sequence 6→8 跳号
      const event = envelope(8, 2, 'cache.job.updated.v1', '{"id":"j1","status":"offlining"}');
      expect(store.apply(event)).assertEqual(EventApplyResult.RECOVERED);
      done();
    });

    it('unknown_type_does_not_crash', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(5, 'cursor-5')));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      const store = new SnapshotStore(client);
      await store.recover();

      const event = envelope(6, 1, 'metadata.job.queued.v1', '{"id":"mj1"}');
      const result = store.apply(event);
      // metadata 资源本地不存在：恢复（不崩溃）
      expect(result).assertEqual(EventApplyResult.RECOVERED);
      done();
    });

    it('shallow_merge_updates_cache_job', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(5, 'cursor-5')));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      const store = new SnapshotStore(client);
      await store.recover();

      const event = envelope(6, 1, 'cache.job.updated.v1',
        '{"id":"j1","status":"offlining","remote_percent":37.5}');
      expect(store.apply(event)).assertEqual(EventApplyResult.APPLIED);
      const jobs = store.cacheJobList;
      expect(jobs.length).assertEqual(1);
      expect(jobs[0].status).assertEqual('offlining');
      expect(jobs[0].remotePercent).assertEqual(37.5);
      done();
    });
  });

  describe('EventClientTest', () => {
    it('close_4409_recovers_and_reconnects', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      const httpTransport = new FakeHttpTransport();
      httpTransport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(5, 'cursor-5')));
      const apiClient = new ApiClient(httpTransport, 'http://127.0.0.1:8000/api/v1', session);
      const store = new SnapshotStore(apiClient);
      const ws = new FakeWebSocketTransport();
      // 重连延迟 10ms，便于测试
      const client = new EventClient(ws, apiClient, store, 10);

      await client.start();
      expect(ws.connectUrls.length).assertEqual(1);

      // 4409：游标过旧 → 拉快照（需再给一个 snapshot 响应）→ 重连
      httpTransport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(9, 'cursor-9')));
      ws.emitClose(4409);
      await new Promise<void>((resolve) => setTimeout(resolve, 300));
      expect(ws.connectUrls.length).assertEqual(2);
      expect(store.version).assertEqual(9);
      done();
    });

    it('close_4401_refreshes_then_reconnects', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      await session.setTokens(new TokenPair('acc', 'ref', 'Bearer', '', ''));
      const httpTransport = new FakeHttpTransport();
      httpTransport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(5, 'cursor-5')));
      // refresh 响应
      httpTransport.responses.push(new QueuedResponse(200,
        '{"access_token":"acc2","refresh_token":"ref2","token_type":"Bearer",' +
        '"access_expires_at":"2026-08-05T00:00:00Z","refresh_expires_at":"2026-09-03T00:00:00Z"}'));
      // recover 快照
      httpTransport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(7, 'cursor-7')));
      const apiClient = new ApiClient(httpTransport, 'http://127.0.0.1:8000/api/v1', session);
      const store = new SnapshotStore(apiClient);
      const ws = new FakeWebSocketTransport();
      const client = new EventClient(ws, apiClient, store, 10);

      await client.start();
      expect(ws.connectUrls.length).assertEqual(1);

      ws.emitClose(4401);
      await new Promise<void>((resolve) => setTimeout(resolve, 400));
      expect(session.getAccessToken()).assertEqual('acc2');
      expect(ws.connectUrls.length).assertEqual(2);
      done();
    });

    it('stop_prevents_reconnect', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      const httpTransport = new FakeHttpTransport();
      httpTransport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(5, 'cursor-5')));
      const apiClient = new ApiClient(httpTransport, 'http://127.0.0.1:8000/api/v1', session);
      const store = new SnapshotStore(apiClient);
      const ws = new FakeWebSocketTransport();
      const client = new EventClient(ws, apiClient, store, 10);

      await client.start();
      client.stop();
      expect(ws.closed).assertTrue();
      // stop 后 close 不再重连
      ws.emitClose(4409);
      await new Promise<void>((resolve) => setTimeout(resolve, 200));
      expect(ws.connectUrls.length).assertEqual(1);
      done();
    });
  });
}
