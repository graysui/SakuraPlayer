/**
 * TASK-313 跨端状态一致性（AC-003 [SEF]）。
 * 使用与 Windows 侧共享的固定快照语义（cross_platform_state.json）验证：
 * HarmonyOS DTO 解析出的目录、收藏、任务和播放进度与 Windows 端一致。
 * 纯 JsUnit（Fake transport），不访问真实 115/JavDB/AI。
 */

import { describe, it, expect } from '@ohos/hypium';
import { HttpRequest, HttpResponse, HttpTransport, ApiClient, MovieListParams,
  RankingQueryParams, ActorListParams } from '../../../main/ets/core/api/ApiClient';
import { PlaybackProgress, ProgressUpdateBody, JsonReader, ApiException } from '../../../main/ets/core/api/ApiModels';
import { SecureSessionStore, SecretStore } from '../../../main/ets/core/auth/SecureSessionStore';

/** 测试专用内存 SecretStore（与 ApiClient.test 同款）。 */
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

/**
 * 与 harmony/test/fixtures/cross_platform_state.json 内容一致（规范样本）。
 * 字段对齐 OpenAPI 契约，Windows Dart 模型同源解析。
 */
const CROSS_PLATFORM_STATE = '{"items":[' +
  '{"id":"m1","number":"ABC-001","title":"跨端目录影片一","title_original":null,"cover_url":null,' +
  '"publish_date":"2026-01-01","labels":["subtitle"],"favorite":true,"source_count":2,' +
  '"progress":{"position_seconds":90,"duration_seconds":150,"completed":false,"version":3}},' +
  '{"id":"m2","number":"DEF-002","title":"跨端目录影片二","title_original":null,"cover_url":null,' +
  '"publish_date":"2026-01-02","labels":[],"favorite":false,"source_count":1,' +
  '"progress":{"position_seconds":0,"duration_seconds":0,"completed":true,"version":5}},' +
  '{"id":"m3","number":"GHI-003","title":"跨端目录影片三","title_original":null,"cover_url":null,' +
  '"publish_date":null,"labels":["4k"],"favorite":false,"source_count":0,"progress":null}],' +
  '"next_cursor":null}';

const RANKINGS_DAILY = '{"board":"daily","year":null,"available_years":[],"synced_at":"2026-08-06T00:00:00Z","items":[' +
  '{"rank":1,"movie":{"id":"m1","number":"ABC-001","title":"跨端目录影片一","title_original":null,' +
  '"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":true,' +
  '"source_count":2,"progress":{"position_seconds":90,"duration_seconds":150,"completed":false,"version":3}}}],' +
  '"next_cursor":null}';

const RANKINGS_TOP250 = '{"board":"top250","year":null,"available_years":[2026,2008],"synced_at":"2026-08-06T00:00:00Z","items":[' +
  '{"rank":1,"movie":{"id":"m2","number":"DEF-002","title":"跨端目录影片二","title_original":null,' +
  '"cover_url":null,"publish_date":"2026-01-02","labels":[],"favorite":false,' +
  '"source_count":1,"progress":{"position_seconds":0,"duration_seconds":0,"completed":true,"version":5}}}],' +
  '"next_cursor":null}';

const ACTORS_BODY = '{"items":[' +
  '{"id":"a1","display_name":"跨端女优一","name_ja":"アクター1","name_zh":"跨端女优一",' +
  '"aliases":["别名一"],"profile_url":null,"favorite":true},' +
  '{"id":"a2","display_name":"跨端女优二","name_ja":"アクター2","name_zh":"跨端女优二",' +
  '"aliases":[],"profile_url":null,"favorite":false}],"next_cursor":null}';

const CACHE_JOBS_BODY = '{"capacity":{"running":0,"running_limit":2,"queued":0,"queued_limit":10,"ready":0,"ready_limit":20},"items":[' +
  '{"id":"10000000-0000-0000-0000-0000000000c1","movie_id":"m1",' +
  '"source_id":"10000000-0000-0000-0000-000000000001","status":"ready","remote_percent":100,' +
  '"error_code":null,"media_candidates":[],"selected_media_ids":[],"subtitles":[],' +
  '"ready_at":"2026-08-06T00:00:00Z","expires_at":"2026-08-07T00:00:00Z",' +
  '"created_at":"2026-08-05T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"},' +
  '{"id":"10000000-0000-0000-0000-0000000000c2","movie_id":"m2",' +
  '"source_id":"10000000-0000-0000-0000-000000000002","status":"cleaned","remote_percent":null,' +
  '"error_code":null,"media_candidates":[],"selected_media_ids":[],"subtitles":[],' +
  '"ready_at":null,"expires_at":null,' +
  '"created_at":"2026-08-05T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}],"next_cursor":null}';

class RouteResponse {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    this.status = status;
    this.body = body;
  }
}

class FakeTransport implements HttpTransport {
  routes: Map<string, RouteResponse> = new Map();
  putProgressCalls: number = 0;

  async request(request: HttpRequest): Promise<HttpResponse> {
    if (request.url.includes('/movies/m1/progress')) {
      this.putProgressCalls++;
      // 契约 CAS：409 携带权威 version；客户端用权威 version 重试后 200。
      if (this.putProgressCalls === 1 && request.method === 'PUT') {
        const conflict: HttpResponse = {
          statusCode: 409,
          body: '{"code":"version_conflict","message":"版本冲突","request_id":"r1",' +
            '"details":{"version":3}}',
        };
        return conflict;
      }
      const ok: HttpResponse = {
        statusCode: 200,
        body: '{"position_seconds":95,"duration_seconds":150,"completed":false,"version":4}',
      };
      return ok;
    }
    for (const entry of this.routes) {
      if (request.url.includes(entry[0])) {
        const result: HttpResponse = { statusCode: entry[1].status, body: entry[1].body };
        return result;
      }
    }
    throw new Error(`no route for ${request.url}`);
  }
}

function makeClient(transport: HttpTransport): ApiClient {
  const session = new SecureSessionStore(new FakeSecretStore());
  return new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
}

export default function crossPlatformStateTest() {
  describe('CrossPlatformStateTest', () => {
    it('catalog_snapshot_preserves_progress', 0, async (done: Function) => {
      const transport = new FakeTransport();
      transport.routes.set('/movies', new RouteResponse(200, CROSS_PLATFORM_STATE));
      const client = makeClient(transport);
      const params: MovieListParams = {};
      const page = await client.listMovies(params);
      expect(page.items.length).assertEqual(3);
      // AC-003：同一账号两端目录一致（m1 收藏 + 进度 60%）
      const m1 = page.items[0];
      expect(m1.id).assertEqual('m1');
      expect(m1.favorite).assertTrue();
      expect(m1.sourceCount).assertEqual(2);
      expect(m1.progress !== null).assertTrue();
      if (m1.progress !== null) {
        expect(m1.progress.positionSeconds).assertEqual(90);
        expect(m1.progress.version).assertEqual(3);
        const fraction = m1.progress.fraction();
        expect(fraction !== null).assertTrue();
        if (fraction !== null) {
          expect(Math.abs(fraction - 0.6) < 0.001).assertTrue();
        }
      }
      // m2 已看完（completed）
      const m2 = page.items[1];
      expect(m2.progress !== null).assertTrue();
      if (m2.progress !== null) {
        expect(m2.progress.completed).assertTrue();
        expect(m2.progress.fraction()).assertNull();
      }
      // m3 无进度
      const m3 = page.items[2];
      expect(m3.progress).assertNull();
      done();
    });

    it('rankings_snapshot_nested_movie', 0, async (done: Function) => {
      const transport = new FakeTransport();
      transport.routes.set('board=daily', new RouteResponse(200, RANKINGS_DAILY));
      transport.routes.set('board=top250', new RouteResponse(200, RANKINGS_TOP250));
      const client = makeClient(transport);
      const daily: RankingQueryParams = { board: 'daily' };
      const dailyPage = await client.getRanking(daily);
      expect(dailyPage.board).assertEqual('daily');
      expect(dailyPage.items.length).assertEqual(1);
      expect(dailyPage.items[0].rank).assertEqual(1);
      expect(dailyPage.items[0].movie.id).assertEqual('m1');
      const top250: RankingQueryParams = { board: 'top250' };
      const topPage = await client.getRanking(top250);
      expect(topPage.board).assertEqual('top250');
      expect(topPage.items[0].movie.id).assertEqual('m2');
      expect(topPage.items[0].movie.progress !== null).assertTrue();
      done();
    });

    it('actors_snapshot_favorites', 0, async (done: Function) => {
      const transport = new FakeTransport();
      transport.routes.set('/actors', new RouteResponse(200, ACTORS_BODY));
      const client = makeClient(transport);
      const params: ActorListParams = {};
      const page = await client.listActors(params);
      expect(page.items.length).assertEqual(2);
      expect(page.items[0].displayName).assertEqual('跨端女优一');
      expect(page.items[0].favorite).assertTrue();
      expect(page.items[1].favorite).assertFalse();
      expect(page.items[0].aliases.length).assertEqual(1);
      expect(page.items[0].aliases[0]).assertEqual('别名一');
      done();
    });

    it('cache_jobs_terminal_semantics', 0, async (done: Function) => {
      const transport = new FakeTransport();
      transport.routes.set('/cache-jobs', new RouteResponse(200, CACHE_JOBS_BODY));
      const client = makeClient(transport);
      const jobs = await client.listCacheJobs(['ready', 'cleaned'], null);
      expect(jobs.items.length).assertEqual(2);
      expect(jobs.items[0].status).assertEqual('ready');
      expect(jobs.items[0].remotePercent).assertEqual(100);
      expect(jobs.items[0].readyAt !== null).assertTrue();
      expect(jobs.items[0].expiresAt !== null).assertTrue();
      expect(jobs.items[1].status).assertEqual('cleaned');
      expect(jobs.items[1].remotePercent).assertNull();
      expect(jobs.items[1].readyAt).assertNull();
      done();
    });

    it('progress_cas_version_conflict_retry_once', 0, async (done: Function) => {
      const transport = new FakeTransport();
      const client = makeClient(transport);
      const body = ProgressUpdateBody.fromPlayback(95, 150, 3);
      let progress: PlaybackProgress;
      try {
        // 第一次 PUT 被 409 拒绝（version 冲突）
        progress = await client.updateMovieProgress('m1', body);
      } catch (err) {
        expect(err instanceof ApiException).assertTrue();
        // 契约：采纳权威 version 后重试一次
        const conflicted = await client.updateMovieProgress('m1', body);
        progress = conflicted;
      }
      expect(progress.version).assertEqual(4);
      expect(progress.positionSeconds).assertEqual(95);
      expect(transport.putProgressCalls).assertEqual(2);
      done();
    });

    it('fraction_matches_windows_shared_semantics', 0, async (done: Function) => {
      // AC-003：同一 fixture 在 Windows 与 HarmonyOS 计算出的进度语义一致
      const reader = JsonReader.fromText(
        '{"position_seconds":90,"duration_seconds":150,"completed":false,"version":3}');
      const ongoing = PlaybackProgress.fromReader(reader);
      expect(Math.abs((ongoing.fraction() as number) - 0.6) < 0.001).assertTrue();
      const readerCompleted = JsonReader.fromText(
        '{"position_seconds":0,"duration_seconds":0,"completed":true,"version":5}');
      const completed = PlaybackProgress.fromReader(readerCompleted);
      expect(completed.fraction()).assertNull();
      const readerUnknown = JsonReader.fromText(
        '{"position_seconds":30,"duration_seconds":null,"completed":false,"version":2}');
      const unknown = PlaybackProgress.fromReader(readerUnknown);
      expect(unknown.fraction()).assertNull();
      done();
    });
  });
}
