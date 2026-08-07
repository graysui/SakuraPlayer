/**
 * TASK-313 可选服务故障隔离（AC-132 [SEF]）。
 * 单个外部元数据源、AI 或 GFriends 故障不使已入库影片、排行榜快照或 115 播放
 * 整体不可用。纯 JsUnit（Fake transport 注入故障路由），无真实外部访问。
 */

import { describe, it, expect } from '@ohos/hypium';
import { HttpRequest, HttpResponse, HttpTransport, ApiClient, MovieListParams,
  RankingQueryParams } from '../../../main/ets/core/api/ApiClient';
import { ApiException } from '../../../main/ets/core/api/ApiModels';
import { PlayRequestStore, PlayRequestPhase } from '../../../main/ets/features/cache/PlayRequestStore';
import { SecureSessionStore, SecretStore } from '../../../main/ets/core/auth/SecureSessionStore';

class SecretStoreShim implements SecretStore {
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

class RouteResponse {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    this.status = status;
    this.body = body;
  }
}

class FailureTransport implements HttpTransport {
  routes: Map<string, RouteResponse> = new Map();
  failed: boolean = false;

  async request(request: HttpRequest): Promise<HttpResponse> {
    for (const entry of this.routes) {
      if (request.url.includes(entry[0])) {
        const result: HttpResponse = { statusCode: entry[1].status, body: entry[1].body };
        return result;
      }
    }
    throw new Error(`no route for ${request.url}`);
  }

  /** 故障注入：metadata/AI/GFriends 相关 URL 返回 5xx/404。 */
  static withFailures(transport: FailureTransport): FailureTransport {
    const failure: HttpResponse = {
      statusCode: 503,
      body: '{"code":"metadata_source_unavailable","message":"上游不可用","request_id":"r1"}',
    };
    transport.routes.set('/admin/metadata-jobs', new RouteResponse(503, failure.body));
    transport.routes.set('/settings/connection-tests', new RouteResponse(503, failure.body));
    transport.routes.set('/images', new RouteResponse(404, 'not found'));
    return transport;
  }
}

function moviesBody(): string {
  // cover_url 指向 GFriends 域名（故障注入 /images 404）；图片加载失败由
  // CatalogImage 组件兜底（TASK-307 CatalogImage.test 覆盖），本用例验证列表 API 不受影响
  return '{"items":[{"id":"m1","number":"ABC-001","title":"故障隔离影片","title_original":null,' +
    '"cover_url":"https://raw.githubusercontent.com/gfriends/gfriends/master/1.jpg",' +
    '"publish_date":"2026-01-01","labels":[],"favorite":false,' +
    '"source_count":1,"progress":null}],"next_cursor":null}';
}

function rankingsBody(): string {
  return '{"board":"daily","year":null,"available_years":[],"synced_at":"2026-08-06T00:00:00Z",' +
    '"items":[{"rank":1,"movie":{"id":"m1","number":"ABC-001",' +
    '"title":"故障隔离影片","title_original":null,"cover_url":null,"publish_date":"2026-01-01",' +
    '"labels":[],"favorite":false,"source_count":1,"progress":null}}],"next_cursor":null}';
}

function playResultStarted(): string {
  return '{"disposition":"started","wait_deadline":"' +
    new Date(Date.now() + 30 * 1000).toISOString() + '",' +
    '"cache_job":{"id":"10000000-0000-0000-0000-0000000000c1","movie_id":"m1",' +
    '"source_id":"10000000-0000-0000-0000-000000000001","status":"submitting",' +
    '"remote_percent":null,"error_code":null,"media_candidates":[],"selected_media_ids":[],' +
    '"subtitles":[],"ready_at":null,"expires_at":null,' +
    '"created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}}';
}

function makeClient(transport: HttpTransport): ApiClient {
  const session = new SecureSessionStore(new SecretStoreShim());
  return new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
}

export default function failureIsolationTest() {
  describe('FailureIsolationTest', () => {
    it('metadata_failure_keeps_catalog_usable', 0, async (done: Function) => {
      const transport = new FailureTransport();
      FailureTransport.withFailures(transport);
      transport.routes.set('/movies', new RouteResponse(200, moviesBody()));
      const client = makeClient(transport);
      // 目录仍可用（已入库影片不受 metadata 源故障影响）
      const params: MovieListParams = {};
      const page = await client.listMovies(params);
      expect(page.items.length).assertEqual(1);
      expect(page.items[0].id).assertEqual('m1');
      // metadata 富化重试隔离失败（不拖垮核心）
      let failed = false;
      try {
        await client.retryMetadataEnrichment(
          '10000000-0000-0000-0000-0000000000e1', ['chinese_description']);
      } catch (err) {
        failed = err instanceof ApiException;
      }
      expect(failed).assertTrue();
      done();
    });

    it('ai_failure_keeps_rankings_snapshot', 0, async (done: Function) => {
      const transport = new FailureTransport();
      FailureTransport.withFailures(transport);
      transport.routes.set('/rankings', new RouteResponse(200, rankingsBody()));
      const client = makeClient(transport);
      // AI probe 失败（connection-tests 503）
      let aiFailed = false;
      try {
        await client.testConnection('ai');
      } catch (err) {
        aiFailed = err instanceof ApiException;
      }
      expect(aiFailed).assertTrue();
      // 排行榜快照仍可用
      const daily: RankingQueryParams = { board: 'daily' };
      const page = await client.getRanking(daily);
      expect(page.board).assertEqual('daily');
      expect(page.items[0].movie.id).assertEqual('m1');
      done();
    });

    it('gfriends_failure_keeps_movie_list', 0, async (done: Function) => {
      const transport = new FailureTransport();
      FailureTransport.withFailures(transport);
      transport.routes.set('/movies', new RouteResponse(200, moviesBody()));
      const client = makeClient(transport);
      // GFriends 图片 404 不阻塞目录列表（封面失败由 CatalogImage 兜底占位）
      const params: MovieListParams = {};
      const page = await client.listMovies(params);
      expect(page.items.length).assertEqual(1);
      expect(page.items[0].title).assertEqual('故障隔离影片');
      done();
    });

    it('playback_survives_metadata_failure', 0, async (done: Function) => {
      const transport = new FailureTransport();
      FailureTransport.withFailures(transport);
      transport.routes.set('/movies/m1/play-requests',
        new RouteResponse(202, playResultStarted()));
      const client = makeClient(transport);
      // 元数据源故障时 115 播放请求仍可用（AC-132：115 播放不整体不可用）
      const store = new PlayRequestStore();
      store.attach(client, null);
      store.submit('m1', '10000000-0000-0000-0000-000000000001');
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 300);
      });
      expect(store.phase).assertEqual(PlayRequestPhase.WAITING);
      expect(store.errorCode).assertNull();
      store.detach();
      done();
    });

    it('combined_failures_core_still_ready', 0, async (done: Function) => {
      const transport = new FailureTransport();
      FailureTransport.withFailures(transport);
      // 精确路由先插（includes 先匹配者优先：/movies 会吞掉 play-requests）
      transport.routes.set('/movies/m1/play-requests',
        new RouteResponse(202, playResultStarted()));
      transport.routes.set('/movies', new RouteResponse(200, moviesBody()));
      transport.routes.set('/rankings', new RouteResponse(200, rankingsBody()));
      const client = makeClient(transport);
      // 三故障同时：目录、榜单、播放全部继续可用
      const params: MovieListParams = {};
      const page = await client.listMovies(params);
      expect(page.items.length).assertEqual(1);
      const daily: RankingQueryParams = { board: 'daily' };
      const ranking = await client.getRanking(daily);
      expect(ranking.items[0].movie.id).assertEqual('m1');
      const store = new PlayRequestStore();
      store.attach(client, null);
      store.submit('m1', '10000000-0000-0000-0000-000000000001');
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 300);
      });
      expect(store.phase).assertEqual(PlayRequestPhase.WAITING);
      store.detach();
      done();
    });
  });
}
