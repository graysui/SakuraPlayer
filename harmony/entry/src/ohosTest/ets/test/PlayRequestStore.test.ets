/**
 * TASK-309 播放请求 Store 测试（60 秒状态机）。
 * - ready / started 59 秒内完成 / 60 秒超时后完成不自动播放 / queued / reused
 * - 幂等键格式与 single-flight 重复点击
 * - 取消二次确认成功与稳定错误保留
 * - detach 后 timer/事件不自动导航
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { CacheJobDetail, TokenPair } from '../../../main/ets/core/api/ApiModels';
import { PlayRequestPhase, PlayRequestStore } from '../../../main/ets/features/cache/PlayRequestStore';

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

  request(request: HttpRequest): Promise<HttpResponse> {
    this.requests.push(request);
    const hit = this.routes.get(request.url);
    if (hit === undefined) {
      return Promise.reject(new Error(`no route for ${request.url}`));
    }
    return Promise.resolve(hit);
  }
}

const BASE = 'http://test/api/v1';
const JOB_ID = '10000000-0000-0000-0000-0000000000c1';
const MOVIE_ID = '10000000-0000-0000-0000-0000000000a1';
const SOURCE_ID = '10000000-0000-0000-0000-0000000000b1';

function cacheJobBody(status: string): string {
  return `{"id":"${JOB_ID}","movie_id":"${MOVIE_ID}","source_id":"${SOURCE_ID}",` +
    `"status":"${status}","remote_percent":null,"error_code":null,"media_candidates":[],` +
    `"selected_media_ids":["10000000-0000-0000-0000-0000000000d1"],"subtitles":[],` +
    `"ready_at":null,"expires_at":null,"created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}`;
}

function playResult(disposition: string, jobStatus: string, deadlineIso: string | null): string {
  return `{"disposition":"${disposition}","wait_deadline":${deadlineIso === null ? 'null' : `"${deadlineIso}"`},` +
    `"cache_job":${cacheJobBody(jobStatus)}}`;
}

function deadlineIn(seconds: number): string {
  return new Date(Date.now() + seconds * 1000).toISOString();
}

class Fixture {
  readonly transport: FakeHttpTransport;
  readonly store: PlayRequestStore;

  constructor() {
    this.transport = new FakeHttpTransport();
    const client = new ApiClient(this.transport, BASE, new FakeSession());
    this.store = new PlayRequestStore();
    this.store.attach(client, null);
  }

  routePlay(statusCode: number, body: string): void {
    this.transport.routes.set(`${BASE}/movies/${MOVIE_ID}/play-requests`, { statusCode: statusCode, body: body });
  }

  routeCancel(statusCode: number, body: string): void {
    this.transport.routes.set(`${BASE}/cache-jobs/${JOB_ID}/cancel`, { statusCode: statusCode, body: body });
  }
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export default function playRequestStoreTest() {
  describe('PlayRequestStore', () => {
  it('ready_disposition_goes_ready_once', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(200, playResult('ready', 'ready', null));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.READY);
    expect(fixture.store.navigationRevision).assertEqual(1);
    // 幂等键格式
    const request = fixture.transport.requests[0];
    const key = request.headers !== undefined ? request.headers['Idempotency-Key'] : null;
    expect(key !== undefined && key !== null).assertTrue();
    if (key !== undefined && key !== null) {
      expect(key.length >= 16 && key.length <= 128).assertTrue();
      expect(/^[A-Za-z0-9._~-]{16,128}$/.test(key)).assertTrue();
    }
    expect(request.url).assertEqual(`${BASE}/movies/${MOVIE_ID}/play-requests`);
    expect(request.body).assertEqual(`{"source_id":"${SOURCE_ID}"}`);
  });

  it('started_waits_with_countdown', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(202, playResult('started', 'submitting', deadlineIn(30)));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.WAITING);
    expect(fixture.store.remainingSeconds > 0).assertTrue();
    expect(fixture.store.remainingSeconds <= 30).assertTrue();
    fixture.store.detach();
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.IDLE);
  });

  it('snapshot_ready_before_deadline_auto_plays_once', 0, () => {
    const deadline = Date.now() + 30000;
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, JOB_ID, deadline,
      Date.now(), JOB_ID, 'ready', null)).assertEqual('auto_play');
    // 非等待/不同 id/不同状态 → 忽略
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.READY, JOB_ID, deadline,
      Date.now(), JOB_ID, 'ready', null)).assertEqual('ignore');
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, 'other-id', deadline,
      Date.now(), JOB_ID, 'ready', null)).assertEqual('ignore');
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, JOB_ID, deadline,
      Date.now(), JOB_ID, 'resolving', null)).assertEqual('ignore');
  });

  it('snapshot_ready_after_deadline_does_not_auto_play', 0, () => {
    const deadline = Date.now() - 1000;
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, JOB_ID, deadline,
      Date.now(), JOB_ID, 'ready', null)).assertEqual('timeout');
  });

  it('snapshot_terminal_states', 0, () => {
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, JOB_ID, Date.now() + 1000,
      Date.now(), JOB_ID, 'failed', 'scrape_failed')).assertEqual('failed');
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, JOB_ID, Date.now() + 1000,
      Date.now(), JOB_ID, 'awaiting_selection', null)).assertEqual('existing');
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, JOB_ID, Date.now() + 1000,
      Date.now(), JOB_ID, 'cleaned', null)).assertEqual('ignore');
    expect(PlayRequestStore.evaluateSnapshot(PlayRequestPhase.WAITING, JOB_ID, Date.now() + 1000,
      Date.now(), JOB_ID, 'detached', null)).assertEqual('ignore');
  });

  it('timeout_after_60s_exits_without_cancel_api', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(202, playResult('started', 'submitting', deadlineIn(1)));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.WAITING);
    // 等 deadline 过（1s）
    await sleep(1500);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.TIMED_OUT);
    expect(fixture.store.remainingSeconds).assertEqual(0);
    // 未调用任何取消 API
    const cancels = fixture.transport.requests.filter((r) => r.url.includes('/cancel')).length;
    expect(cancels).assertEqual(0);
  });

  it('queued_exits_immediately', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(202, playResult('queued', 'queued', null));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.QUEUED);
  });

  it('reused_ready_plays_but_reused_other_shows_existing', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(200, playResult('reused', 'ready', null));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.READY);
    expect(fixture.store.navigationRevision).assertEqual(1);
    const fixture2 = new Fixture();
    fixture2.routePlay(200, playResult('reused', 'resolving', null));
    fixture2.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect('phase=' + fixture2.store.phase + ' error=' + fixture2.store.errorCode).
      assertEqual(`phase=${PlayRequestPhase.EXISTING} error=null`);
  });

  it('duplicate_submit_while_in_flight_is_ignored', 0, async () => {
    const fixture = new Fixture();
    // 请求挂起（不返回）
    fixture.routePlay(202, playResult('started', 'submitting', deadlineIn(30)));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.SUBMITTING);
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(30);
    // 只发了一个请求
    const posts = fixture.transport.requests.filter((r) => r.url.includes('/play-requests')).length;
    expect(posts).assertEqual(1);
  });

  it('cancel_confirmed_success', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(202, playResult('started', 'submitting', deadlineIn(30)));
    fixture.routeCancel(202, cacheJobBody('cancelling'));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.WAITING);
    fixture.store.cancel(true);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.CANCELLED);
    const cancel = fixture.transport.requests.find((r) => r.url.includes('/cancel'));
    expect(cancel !== undefined && cancel.body).assertEqual('{"confirmed":true}');
  });

  it('cancel_stable_error_keeps_waiting', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(202, playResult('started', 'submitting', deadlineIn(30)));
    fixture.routeCancel(409, '{"code":"cache_active_lease","message":"playing","request_id":"r1"}');
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    fixture.store.cancel(true);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.WAITING);
    expect(fixture.store.cancelError).assertEqual('cache_active_lease');
    expect(fixture.store.cancelling).assertFalse();
  });

  it('detach_stops_timer_and_clears_state', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(202, playResult('started', 'submitting', deadlineIn(30)));
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.WAITING);
    fixture.store.detach();
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.IDLE);
    expect(fixture.store.job).assertNull();
    // 等 2 秒确认 timer 已停（无残留 tick）
    await sleep(2100);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.IDLE);
  });

  it('failed_play_request_sets_error', 0, async () => {
    const fixture = new Fixture();
    fixture.routePlay(500, '{"code":"internal_error","message":"x","request_id":"r1"}');
    fixture.store.submit(MOVIE_ID, SOURCE_ID);
    await sleep(200);
    expect(fixture.store.phase).assertEqual(PlayRequestPhase.FAILED);
    expect(fixture.store.errorCode).assertEqual('internal_error');
  });

  it('idempotency_keys_are_unique', 0, () => {
    const a = PlayRequestStore.newIdempotencyKey();
    const b = PlayRequestStore.newIdempotencyKey();
    expect(a !== b).assertTrue();
    expect(/^[A-Za-z0-9._~-]{16,128}$/.test(a)).assertTrue();
    expect(a.length).assertEqual(36);
  });
});
}
