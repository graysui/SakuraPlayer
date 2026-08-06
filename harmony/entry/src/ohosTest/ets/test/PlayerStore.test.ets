/**
 * TASK-310 PlayerStore 测试：模式/UA/会话生命周期 fixture（不连接物理真机）。
 * - original 初始新 session + 固定 UA + stream_url 绝对化 + 起始位置
 * - 模式切换新 session 原子替换 / 失败保留旧会话
 * - 过期重签一次不循环；未过期错误不重签
 * - generation 隔离；dispose release
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { TokenPair } from '../../../main/ets/core/api/ApiModels';
import { PlaybackMode, PlayerPhase, PlayerStore, PlayerSurface } from '../../../main/ets/features/playback/PlayerStore';

const BASE = 'http://test/api/v1';
const ORIGIN = 'http://test';
const JOB_ID = '10000000-0000-0000-0000-0000000000c1';
const MEDIA_ID = '10000000-0000-0000-0000-0000000000d1';
const SESSION_ID = '20000000-0000-0000-0000-0000000000e1';
const UA = 'SakuraPlayer/1.0 (HarmonyOS)';

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

class SurfaceLoadCall {
  readonly url: string;
  readonly headers: Record<string, string>;
  readonly startMs: number;

  constructor(url: string, headers: Record<string, string>, startMs: number) {
    this.url = url;
    this.headers = headers;
    this.startMs = startMs;
  }
}

class RecordingSurface implements PlayerSurface {
  loadCalls: SurfaceLoadCall[] = [];
  playCount: number = 0;
  pauseCount: number = 0;
  seekCalls: number[] = [];
  speedCalls: number[] = [];
  released: boolean = false;
  loadError: Error | null = null;

  load(url: string, headers: Record<string, string>, startPositionMs: number): Promise<void> {
    this.loadCalls.push(new SurfaceLoadCall(url, headers, startPositionMs));
    if (this.loadError !== null) {
      return Promise.reject(this.loadError);
    }
    return Promise.resolve();
  }

  play(): void {
    this.playCount++;
  }

  pause(): void {
    this.pauseCount++;
  }

  seek(timeMs: number): void {
    this.seekCalls.push(timeMs);
  }

  setSpeed(speed: number): void {
    this.speedCalls.push(speed);
  }

  release(): void {
    this.released = true;
  }
}

function manifestBody(mode: string, extra: string, expiresAt?: string): string {
  // 相对时间：默认 24 小时后过期（避免测试时间炸弹）
  const defaultExpires = new Date(Date.now() + 24 * 3600 * 1000).toISOString();
  const expires = expiresAt === undefined ? defaultExpires : expiresAt;
  return `{"session_id":"${SESSION_ID}","cache_job_id":"${JOB_ID}","mode":"${mode}",` +
    `"platform":"harmonyos","stream_url":"/playback/streams/${SESSION_ID}?expires=1&signature=abcd",` +
    `"expires_at":"${expires}","subtitle_cache_expires_at":"2026-08-07T12:00:00Z",` +
    `"required_user_agent":"${UA}","embedded_tracks_source":"client_player",` +
    `"media_queue":[{"session_id":"${SESSION_ID}","media":{"id":"${MEDIA_ID}"},` +
    `"stream_url":"/playback/streams/${SESSION_ID}","sequence_no":1}],` +
    `"subtitles":[],"progress":${extra}}`;
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

class Fixture {
  readonly transport: FakeHttpTransport;
  readonly surface: RecordingSurface;
  readonly store: PlayerStore;

  constructor() {
    this.transport = new FakeHttpTransport();
    this.surface = new RecordingSurface();
    const client = new ApiClient(this.transport, BASE, new FakeSession());
    this.store = new PlayerStore();
    this.store.attach(client, ORIGIN, this.surface, '30000000-0000-0000-0000-0000000000f1');
  }

  routeSession(mode: string, extra: string, expiresAt?: string): void {
    this.transport.routes.set(`${BASE}/cache-jobs/${JOB_ID}/playback-sessions`,
      { statusCode: 201, body: manifestBody(mode, extra, expiresAt) });
  }
}

export default function playerStoreTest() {
  describe('PlayerStore', () => {
    it('enter_creates_original_session_and_loads_with_fixed_ua', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      expect(fixture.store.mode).assertEqual(PlaybackMode.ORIGINAL);
      expect(fixture.store.phase).assertEqual(PlayerPhase.CREATING_SESSION);
      // surface.load 已带固定 UA + 绝对化 URL + 起始位置 0
      expect(fixture.surface.loadCalls.length).assertEqual(1);
      expect(fixture.surface.loadCalls[0].url).assertEqual(
        `${ORIGIN}/playback/streams/${SESSION_ID}?expires=1&signature=abcd`);
      expect(fixture.surface.loadCalls[0].headers['User-Agent']).assertEqual(UA);
      expect(fixture.surface.loadCalls[0].startMs).assertEqual(0);
      // 请求 body 校验 mode/platform/client_instance_id
      const request = fixture.transport.requests[0];
      const body = request.body ?? '';
      expect(body.includes('"mode":"original"')).assertTrue();
      expect(body.includes('"platform":"harmonyos"')).assertTrue();
      expect(body.includes('"media_id":"' + MEDIA_ID + '"')).assertTrue();
      // prepared → play
      fixture.store.onSurfacePrepared();
      expect(fixture.store.phase).assertEqual(PlayerPhase.PLAYING);
      expect(fixture.surface.playCount).assertEqual(1);
    });

    it('manifest_mode_mismatch_is_protocol_error', 0, async () => {
      const fixture = new Fixture();
      // 请求 original 但 manifest 返回 compatibility → 协议错误
      fixture.routeSession('compatibility', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      expect(fixture.store.phase).assertEqual(PlayerPhase.ERROR);
      expect(fixture.store.errorCode).assertEqual('client_protocol_error');
      expect(fixture.surface.loadCalls.length).assertEqual(0);
    });

    it('switch_mode_creates_new_session_and_reloads', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      fixture.store.onSurfacePrepared();
      expect(fixture.surface.loadCalls.length).assertEqual(1);
      // 切 compatibility：新 session + 新 load
      fixture.routeSession('compatibility', 'null');
      fixture.store.switchMode(PlaybackMode.COMPATIBILITY);
      // 轮询等待模式切换完成（模拟器慢）
      let switched = false;
      for (let i = 0; i < 60; i++) {
        if (fixture.store.mode === PlaybackMode.COMPATIBILITY) {
          switched = true;
          break;
        }
        await sleep(50);
      }
      expect('switched=' + switched).assertEqual('switched=true');
      expect(fixture.surface.loadCalls.length).assertEqual(2);
      expect(fixture.transport.requests.length).assertEqual(2);
      // 切回 original
      fixture.routeSession('original', 'null');
      fixture.store.switchMode(PlaybackMode.ORIGINAL);
      // 先确认请求已发出
      expect(fixture.transport.requests.length).assertEqual(3);
      let switchedBack = false;
      for (let i = 0; i < 60; i++) {
        if (fixture.store.mode === PlaybackMode.ORIGINAL) {
          switchedBack = true;
          break;
        }
        await sleep(50);
      }
      expect('switched back=' + switchedBack).assertEqual('switched back=true');
      expect(fixture.surface.loadCalls.length).assertEqual(3);
    });

    it('switch_mode_failure_keeps_old_session', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      fixture.store.onSurfacePrepared();
      const beforeUrl = fixture.surface.loadCalls[0].url;
      // 切 compatibility 失败（500）
      fixture.transport.routes.set(`${BASE}/cache-jobs/${JOB_ID}/playback-sessions`,
        { statusCode: 500, body: '{"code":"internal_error","message":"x","request_id":"r1"}' });
      fixture.store.switchMode(PlaybackMode.COMPATIBILITY);
      await sleep(50);
      expect(fixture.store.phase).assertEqual(PlayerPhase.ERROR);
      expect(fixture.store.errorCode).assertEqual('internal_error');
      // 旧会话保留（未 reload 新 URL）
      expect(fixture.store.mode).assertEqual(PlaybackMode.ORIGINAL);
      expect(fixture.surface.loadCalls.length).assertEqual(1);
      expect(fixture.surface.loadCalls[0].url).assertEqual(beforeUrl);
    });

    it('expired_manifest_reissues_once_same_mode', 0, async () => {
      const fixture = new Fixture();
      // expires_at 为过去（已过期）
      const past = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
      fixture.routeSession('original', 'null', past);
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      expect(fixture.store.session !== null).assertTrue();
      // 直接触发 surface error（session 已过期）
      fixture.store.onSurfaceError(new Error('stream failed'));
      await sleep(50);
      // 重签一次（同 mode）
      expect(fixture.transport.requests.length).assertEqual(2);
      expect(fixture.surface.loadCalls.length).assertEqual(2);
      // 再次错误：不循环重签
      fixture.store.onSurfaceError(new Error('stream failed again'));
      await sleep(50);
      expect(fixture.transport.requests.length).assertEqual(2);
      expect(fixture.store.phase).assertEqual(PlayerPhase.ERROR);
    });

    it('unexpired_error_does_not_reissue', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      // session 未过期（2026-08-07）→ 普通错误
      fixture.store.onSurfaceError(new Error('decode failed'));
      await sleep(50);
      expect(fixture.transport.requests.length).assertEqual(1);
      expect(fixture.store.phase).assertEqual(PlayerPhase.ERROR);
      expect(fixture.store.errorCode).assertEqual('client_transport_error');
    });

    it('retry_creates_fresh_session', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      fixture.store.onSurfaceError(new Error('x'));
      await sleep(50);
      expect(fixture.store.phase).assertEqual(PlayerPhase.ERROR);
      // 显式重试：新 session
      fixture.routeSession('original', 'null');
      fixture.store.retry();
      await sleep(50);
      expect(fixture.transport.requests.length).assertEqual(2);
      expect(fixture.store.phase).assertEqual(PlayerPhase.CREATING_SESSION);
    });

    it('progress_seed_seeks_to_position', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original',
        '{"position_seconds":120,"duration_seconds":600,"completed":false,"version":3}');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      expect(fixture.surface.loadCalls[0].startMs).assertEqual(120000);
    });

    it('controls_play_pause_seek_speed', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      fixture.store.onSurfacePrepared();
      fixture.store.pause();
      expect(fixture.store.phase).assertEqual(PlayerPhase.PAUSED);
      expect(fixture.surface.pauseCount).assertEqual(1);
      fixture.store.play();
      expect(fixture.store.phase).assertEqual(PlayerPhase.PLAYING);
      expect(fixture.surface.playCount).assertEqual(2);
      fixture.store.seek(30000);
      expect(fixture.surface.seekCalls.length).assertEqual(1);
      expect(fixture.surface.seekCalls[0]).assertEqual(30000);
      fixture.store.setSpeed(1.5);
      expect(fixture.surface.speedCalls.length).assertEqual(1);
      expect(fixture.surface.speedCalls[0]).assertEqual(1.5);
      expect(fixture.store.speed).assertEqual(1.5);
    });

    it('dispose_releases_surface_without_cancelling_job', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      fixture.store.dispose();
      expect(fixture.surface.released).assertTrue();
      expect(fixture.store.phase).assertEqual(PlayerPhase.RELEASED);
      expect(fixture.store.session).assertNull();
      // 返回只结束页面 session，不取消/清理 CacheJob（契约 §1）
      const cancels = fixture.transport.requests.filter((r) => r.url.includes('/cancel')).length;
      expect(cancels).assertEqual(0);
    });

    it('load_failure_reports_error', 0, async () => {
      const fixture = new Fixture();
      fixture.routeSession('original', 'null');
      fixture.surface.loadError = new Error('load failed');
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      expect(fixture.store.phase).assertEqual(PlayerPhase.ERROR);
      expect(fixture.store.errorCode).assertEqual('client_transport_error');
    });

    it('start_media_must_exist_in_queue', 0, async () => {
      const fixture = new Fixture();
      // queue 只含别的 media id（不含 MEDIA_ID）
      const body = manifestBody('original', 'null');
      const queue = body.replace(MEDIA_ID, '40000000-0000-0000-0000-0000000000a2');
      fixture.transport.routes.set(`${BASE}/cache-jobs/${JOB_ID}/playback-sessions`,
        { statusCode: 201, body: queue });
      fixture.store.enter(JOB_ID, MEDIA_ID);
      await sleep(50);
      expect(fixture.store.phase).assertEqual(PlayerPhase.ERROR);
      expect(fixture.store.errorCode).assertEqual('client_protocol_error');
    });

    it('resolve_stream_url_validates_origin', 0, () => {
      expect(PlayerStore.resolveStreamUrl('http://test',
        '/playback/streams/x')).assertEqual('http://test/playback/streams/x');
      expect(PlayerStore.resolveStreamUrl('http://test',
        'http://test/playback/streams/x')).assertEqual('http://test/playback/streams/x');
      // 前缀伪装/端口/userinfo 全部拒绝（P1-1 安全）
      const evil: string[] = [
        'http://evil.example/x',
        'http://test.evil/x',
        'http://test:8080/x',
        'http://test@evil.com/x',
        '//evil/x',
        'https://test/x',
      ];
      for (const url of evil) {
        let threw = false;
        try {
          PlayerStore.resolveStreamUrl('http://test', url);
        } catch (err) {
          threw = true;
        }
        expect('reject ' + url + '=' + threw).assertEqual(`reject ${url}=true`);
      }
    });
  });
}
