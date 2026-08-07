/**
 * TASK-311 ProgressStore 测试：15 秒心跳/version CAS/409 权威覆盖/完成阈值上报/flush。
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { PlaybackProgress, ProgressUpdateBody, TokenPair } from '../../../main/ets/core/api/ApiModels';
import { ProgressStore } from '../../../main/ets/features/playback/ProgressStore';

const SESSION_ID = '20000000-0000-0000-0000-0000000000e1';
const MOVIE_ID = '10000000-0000-0000-0000-0000000000a1';
const CLIENT_ID = '30000000-0000-0000-0000-0000000000f1';

class FakeSession implements SessionProvider {
  getAccessToken(): string | null {
    return 'fake-access';
  }

  getRefreshToken(): string | null {
    return 'fake-refresh';
  }

  setTokens(pair: TokenPair): Promise<void> {
    return Promise.resolve();
  }

  clearTokens(): Promise<void> {
    return Promise.resolve();
  }
}

class FakeHttpTransport implements HttpTransport {
  routes: Map<string, HttpResponse> = new Map();
  requests: HttpRequest[] = [];
  /** 按序响应（优先于 routes；用于 409→200 序列）。 */
  sequence: HttpResponse[] = [];
  private sequenceIndex: number = 0;

  request(request: HttpRequest): Promise<HttpResponse> {
    this.requests.push(request);
    if (this.sequenceIndex < this.sequence.length) {
      const resp = this.sequence[this.sequenceIndex];
      this.sequenceIndex++;
      return Promise.resolve(resp);
    }
    const hit = this.routes.get(request.url);
    if (hit === undefined) {
      return Promise.reject(new Error(`no route for ${request.url}`));
    }
    return Promise.resolve(hit);
  }
}

function heartbeatBody(lease: string | null, progressBody: string | null): string {
  const progress = progressBody === null ? 'null' : progressBody;
  return `{"lease_expires_at":${lease === null ? 'null' : `"${lease}"`},"progress":${progress}}`;
}

function progressBody(position: number, duration: number | null, completed: boolean, version: number): string {
  return `{"position_seconds":${position},"duration_seconds":${duration === null ? 'null' : duration},` +
    `"completed":${completed},"version":${version}}`;
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

class Fixture {
  readonly transport: FakeHttpTransport;
  readonly store: ProgressStore;

  constructor() {
    this.transport = new FakeHttpTransport();
    const client = new ApiClient(this.transport, 'http://test/api/v1', new FakeSession());
    this.store = new ProgressStore();
    this.store.attach(client, SESSION_ID, MOVIE_ID, CLIENT_ID);
  }

  routeHeartbeat(status: number, body: string): void {
    this.transport.routes.set(`http://test/api/v1/playback/sessions/${SESSION_ID}/heartbeat`,
      { statusCode: status, body: body });
  }
}

export default function progressStoreTest() {
  describe('ProgressStore', () => {
    it('start_uses_manifest_version_and_starts_heartbeat_timer', 0, async () => {
      const fixture = new Fixture();
      fixture.routeHeartbeat(200, heartbeatBody('t', progressBody(10, 600, false, 1)));
      const initial = new PlaybackProgress(10, 600, false, 3);
      fixture.store.start(initial);
      expect(fixture.store.version).assertEqual(3);
      expect(fixture.store.heartbeating).assertTrue();
      expect(fixture.store.completed).assertFalse();
      fixture.store.stop();
    });

    it('heartbeat_with_progress_updates_authoritative', 0, async () => {
      const fixture = new Fixture();
      fixture.routeHeartbeat(200, heartbeatBody('t', progressBody(120, 600, false, 2)));
      fixture.store.start(new PlaybackProgress(0, 600, false, 1));
      await fixture.store.submit(new ProgressUpdateBody(120, 600, 1));
      expect(fixture.store.version).assertEqual(2);
      const auth = fixture.store.authoritative;
      expect(auth !== null).assertTrue();
      if (auth !== null) {
        expect(auth.positionSeconds).assertEqual(120);
        expect(auth.version).assertEqual(2);
      }
      fixture.store.stop();
    });

    it('unknown_duration_uses_null_not_zero', 0, async () => {
      const fixture = new Fixture();
      fixture.routeHeartbeat(200, heartbeatBody('t', progressBody(30, null, false, 2)));
      fixture.store.start(new PlaybackProgress(0, null, false, 1));
      fixture.store.setLatestProgress(30000, 0);
      await fixture.store.flush();
      // 请求体 duration_seconds 为 null
      const request = fixture.transport.requests[0];
      const body = request.body ?? '';
      expect(body.includes('"duration_seconds":null')).assertTrue();
      fixture.store.stop();
    });

    it('flush_playing_false_ends_lease', 0, async () => {
      const fixture = new Fixture();
      fixture.routeHeartbeat(200, heartbeatBody(null, progressBody(50, 600, false, 2)));
      fixture.store.start(new PlaybackProgress(0, 600, false, 1));
      fixture.store.setLatestProgress(50000, 600000);
      await fixture.store.flush();
      const request = fixture.transport.requests[0];
      const body = request.body ?? '';
      expect(body.includes('"playing":false')).assertTrue();
      expect(body.includes('"playing":true')).assertFalse();
      fixture.store.stop();
    });

    it('version_conflict_adopts_authoritative_and_retries_once', 0, async () => {
      const fixture = new Fixture();
      // 序列路由：第一次 409（权威 version=5），重试 200（version=6）
      const conflict: HttpResponse = { statusCode: 409,
        body: `{"code":"progress_version_conflict","message":"v","request_id":"r1",` +
          `"details":{"progress":${progressBody(100, 600, false, 5)}}}` };
      const ok: HttpResponse = { statusCode: 200,
        body: heartbeatBody('t', progressBody(100, 600, false, 6)) };
      fixture.transport.sequence = [conflict, ok];
      fixture.store.start(new PlaybackProgress(0, 600, false, 1));
      await fixture.store.submit(new ProgressUpdateBody(90, 600, 1));
      // 重试是异步链（提交不等重试）：等微任务完成
      await sleep(50);
      // 409 → 权威 version 5 → 重试一次（第二次 200 → version 6）
      expect(fixture.transport.requests.length).assertEqual(2);
      const retryBody = fixture.transport.requests[1].body ?? '';
      expect(retryBody.includes('"version":5')).assertTrue();
      expect(fixture.store.version).assertEqual(6);
      fixture.store.stop();
    });

    it('version_conflict_does_not_retry_forever', 0, async () => {
      const fixture = new Fixture();
      // 服务端持续 409（多端并发推进 version）：只重试一次，第三次请求不再发出
      const conflict: HttpResponse = { statusCode: 409,
        body: `{"code":"progress_version_conflict","message":"v","request_id":"r1",` +
          `"details":{"progress":${progressBody(100, 600, false, 5)}}}` };
      fixture.transport.sequence = [conflict, conflict];
      fixture.store.start(new PlaybackProgress(0, 600, false, 1));
      await fixture.store.submit(new ProgressUpdateBody(90, 600, 1));
      await sleep(50);
      // 仅 2 个请求（原始 + 一次重试），不循环
      expect(fixture.transport.requests.length).assertEqual(2);
      expect(fixture.store.lastError).assertEqual('progress_version_conflict');
      expect(fixture.store.version).assertEqual(5);
      fixture.store.stop();
    });

    it('state_conflict_stops_heartbeat', 0, async () => {
      const fixture = new Fixture();
      fixture.routeHeartbeat(409, '{"code":"state_conflict","message":"s","request_id":"r1"}');
      fixture.store.start(new PlaybackProgress(0, 600, false, 1));
      await fixture.store.submit(new ProgressUpdateBody(10, 600, 1));
      expect(fixture.store.heartbeating).assertFalse();
      expect(fixture.store.lastError).assertEqual('state_conflict');
    });

    it('completed_authoritative_updates_local', 0, async () => {
      const fixture = new Fixture();
      fixture.routeHeartbeat(200, heartbeatBody('t', progressBody(0, 600, true, 4)));
      fixture.store.start(new PlaybackProgress(570, 600, false, 3));
      expect(fixture.store.completed).assertFalse();
      await fixture.store.submit(new ProgressUpdateBody(590, 600, 3));
      expect(fixture.store.completed).assertTrue();
      expect(fixture.store.authoritative !== null).assertTrue();
      if (fixture.store.authoritative !== null) {
        expect(fixture.store.authoritative.positionSeconds).assertEqual(0);
      }
      fixture.store.stop();
    });

    it('stop_clears_timer', 0, async () => {
      const fixture = new Fixture();
      fixture.routeHeartbeat(200, heartbeatBody('t', null));
      fixture.store.start(null);
      expect(fixture.store.version).assertEqual(0);
      fixture.store.stop();
      expect(fixture.store.heartbeating).assertFalse();
      expect(fixture.store.lastError).assertNull();
    });

    it('heartbeat_failure_does_not_stop_loop', 0, async () => {
      const fixture = new Fixture();
      // 路由缺失 → 传输错误 → lastError 设置但 heartbeating 保持
      fixture.store.start(null);
      await fixture.store.submit(new ProgressUpdateBody(10, 600, 0));
      expect(fixture.store.lastError).assertEqual('client_transport_error');
      expect(fixture.store.heartbeating).assertTrue();
      fixture.store.stop();
    });
  });
}
