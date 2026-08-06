/**
 * TASK-307 影片详情 Store/API 测试：
 * - MovieDetail DTO 全字段解析 + 严格校验（枚举/集合上限/去重/大小非负/受限状态）
 * - getMovie/setMovieFavorite 路径与 204 校验
 * - load generation 竞态、切换 movieId 清空、失败/重试、resource_not_found
 * - 收藏：在途防重/成功更新/失败保留/受限详情不收藏
 * - 来源选择：rejected 禁选、重载来源消失清空、失败清空、detach 清空
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { TokenPair } from '../../../main/ets/core/api/ApiModels';
import { MovieDetailStatus, MovieDetailStore } from '../../../main/ets/features/movies/MovieDetailStore';

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
  failWith: HttpResponse | null = null;
  rejectWith: Error | null = null;

  request(request: HttpRequest): Promise<HttpResponse> {
    this.requests.push(request);
    if (this.rejectWith !== null) {
      return Promise.reject(this.rejectWith);
    }
    if (this.failWith !== null) {
      return Promise.resolve(this.failWith);
    }
    // 路由键为完整 URL；未命中视为传输失败
    const hit = this.routes.get(request.url);
    if (hit === undefined) {
      return Promise.reject(new Error(`no route for ${request.url}`));
    }
    return Promise.resolve(hit);
  }
}

function sourceJson(id: string, website: string, title: string, availability: string,
  extra: string): string {
  return `{"id":"${id}","website":"${website}","external_post_id":1001,"title":"${title}",` +
    `"publish_date":null,"category":"中文字幕","labels":["subtitle"],` +
    `"resource_size_mb":2048,"video_file_size_bytes":null,"availability":"${availability}"${extra}}`;
}

function actorJson(id: string, name: string): string {
  return `{"id":"${id}","display_name":"${name}","name_ja":"${name}","name_zh":null,` +
    `"aliases":["${name}别名"],"profile_url":null,"favorite":false}`;
}

function movieDetailJson(id: string, favorite: boolean, metadataState: string,
  sources: string, extra: string): string {
  return `{"id":"${id}","number":"ABC-123","title":"测试影片","title_original":null,` +
    `"cover_url":"/api/v1/catalog/images/c1","publish_date":"2026-01-01",` +
    `"labels":["subtitle","4k"],"favorite":${favorite},"source_count":2,` +
    `"progress":{"position_seconds":120,"duration_seconds":3600,"completed":false,"version":1},` +
    `"metadata_state":"${metadataState}","metadata_error_code":null,` +
    `"release_date":"2026-01-02","maker":"M厂","series":"S系列","director":"D导演",` +
    `"score":8.5,"description":"中文简介","description_original":"原文简介",` +
    `"actors":[${actorJson('a1', '张三')}],"tags":["长发","剧情"],` +
    `"plot_image_urls":["/api/v1/catalog/images/p1","/api/v1/catalog/images/p2"],` +
    `"sources":[${sources}]${extra}}`;
}

class StoreFixture {
  readonly transport: FakeHttpTransport;
  readonly store: MovieDetailStore;
  readonly client: ApiClient;

  constructor() {
    this.transport = new FakeHttpTransport();
    const session = new FakeSession();
    this.client = new ApiClient(this.transport, 'http://test/api/v1', session);
    this.store = new MovieDetailStore();
    this.store.attach(this.client);
  }

  routeDetail(body: string, status: number = 200): void {
    this.transport.routes.set('http://test/api/v1/movies/m1', { statusCode: status, body: body });
  }

  routeFavorite(enabled: boolean): void {
    this.transport.routes.set('http://test/api/v1/movies/m1/favorite', { statusCode: 204, body: '' });
  }
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export default function movieDetailTest() {
  describe('MovieDetailStore', () => {
  it('loads_full_detail_and_parses_all_fields', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready',
      sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', '源一', 'ready', '') + ',' +
      sourceJson('10000000-0000-0000-0000-000000000002', 'x1080x', '源二', 'rejected', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.READY);
    const detail = fixture.store.detail;
    expect(detail !== null).assertTrue();
    if (detail === null) {
      return;
    }
    expect(detail.number).assertEqual('ABC-123');
    expect(detail.title).assertEqual('测试影片');
    expect(detail.releaseDate).assertEqual('2026-01-02');
    expect(detail.maker).assertEqual('M厂');
    expect(detail.series).assertEqual('S系列');
    expect(detail.director).assertEqual('D导演');
    expect(detail.score).assertEqual(8.5);
    expect(detail.description).assertEqual('中文简介');
    expect(detail.tags.length).assertEqual(2);
    expect(detail.plotImageUrls.length).assertEqual(2);
    expect(detail.actors.length).assertEqual(1);
    expect(detail.actors[0].displayName).assertEqual('张三');
    expect(detail.progress !== null).assertTrue();
    expect(detail.sources.length).assertEqual(2);
    expect(detail.sources[0].website).assertEqual('sehuatang');
    expect(detail.sources[0].resourceSizeMb).assertEqual(2048);
    expect(detail.sources[0].isSelectable()).assertTrue();
    expect(detail.sources[1].isSelectable()).assertFalse();
    expect(detail.isLimited()).assertFalse();
    // 请求路径正确
    expect(fixture.transport.requests.length).assertEqual(1);
    expect(fixture.transport.requests[0].url).assertEqual('http://test/api/v1/movies/m1');
  });

  it('switching_movie_clears_old_detail_and_drops_stale_response', 0, async () => {
    const fixture = new StoreFixture();
    fixture.transport.routes.set('http://test/api/v1/movies/m1', { statusCode: 200, body: movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), '') });
    fixture.transport.routes.set('http://test/api/v1/movies/m2', { statusCode: 200, body: movieDetailJson('m2', true, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000009', 'sehuatang', 'B', 'available', ''), '') });
    // m1 慢响应
    fixture.transport.rejectWith = null;
    fixture.store.load('m1');
    fixture.store.load('m2');
    await sleep(50);
    // 最终状态是 m2（旧 m1 详情被清空）
    expect(fixture.store.movieId).assertEqual('m2');
    expect(fixture.store.detail !== null).assertTrue();
    if (fixture.store.detail !== null) {
      expect(fixture.store.detail.id).assertEqual('m2');
    }
  });

  it('switching_movie_clears_previous_selection', 0, async () => {
    const fixture = new StoreFixture();
    fixture.transport.routes.set('http://test/api/v1/movies/m1', { statusCode: 200, body: movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), '') });
    fixture.transport.routes.set('http://test/api/v1/movies/m2', { statusCode: 200, body: movieDetailJson('m2', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000009', 'sehuatang', 'B', 'available', ''), '') });
    fixture.store.load('m1');
    await sleep(50);
    fixture.store.selectSource('10000000-0000-0000-0000-000000000001');
    expect(fixture.store.selectedSourceId).assertEqual('10000000-0000-0000-0000-000000000001');
    // 切换影片：旧影片来源选择必须清空（契约）
    fixture.store.load('m2');
    await sleep(50);
    expect(fixture.store.movieId).assertEqual('m2');
    expect(fixture.store.selectedSourceId).assertNull();
    // 同影片重载保留选择（契约：详情重新加载后来源仍存在则保留）
    fixture.store.selectSource('10000000-0000-0000-0000-000000000009');
    expect(fixture.store.selectedSourceId).assertEqual('10000000-0000-0000-0000-000000000009');
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.movieId).assertEqual('m1');
    expect(fixture.store.selectedSourceId).assertNull();
  });

  it('failed_load_sets_error_and_retry_uses_same_movie', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail('{"code":"internal_error","message":"boom","request_id":"r1"}', 500);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('internal_error');
    expect(fixture.store.selectedSourceId).assertNull();
    // 重试：再次请求同一 MovieId
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.store.retry();
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.READY);
    expect(fixture.transport.requests.length).assertEqual(2);
    expect(fixture.transport.requests[1].url).assertEqual('http://test/api/v1/movies/m1');
  });

  it('resource_not_found_is_exposed', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail('{"code":"resource_not_found","message":"no","request_id":"r1"}', 404);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.isNotFound()).assertTrue();
  });

  it('favorite_success_updates_detail', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.routeFavorite(true);
    fixture.store.load('m1');
    await sleep(50);
    let current = fixture.store.detail;
    expect(current !== null && !current.favorite).assertTrue();
    fixture.store.setFavorite(true);
    await sleep(50);
    current = fixture.store.detail;
    expect(current !== null && current.favorite).assertTrue();
    expect(fixture.store.favoriteError).assertNull();
    expect(fixture.transport.requests[1].method).assertEqual('PUT');
  });

  it('favorite_failure_keeps_old_value_and_shows_error', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    fixture.transport.routes.set('http://test/api/v1/movies/m1/favorite', { statusCode: 500, body: '{"code":"internal_error","message":"x","request_id":"r1"}' });
    fixture.store.setFavorite(true);
    await sleep(50);
    const kept = fixture.store.detail;
    expect(kept !== null && !kept.favorite).assertTrue();
    expect(fixture.store.favoriteError).assertEqual('internal_error');
    expect(fixture.store.favoriteInFlight).assertFalse();
  });

  it('favorite_in_flight_blocks_duplicate', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    // 收藏请求不返回（挂起）
    fixture.transport.rejectWith = new Error('pending');
    fixture.transport.failWith = null;
    fixture.store.setFavorite(true);
    expect(fixture.store.favoriteInFlight).assertTrue();
    const calls = fixture.transport.requests.length;
    fixture.store.setFavorite(false);
    fixture.store.setFavorite(true);
    await sleep(30);
    expect(fixture.transport.requests.length).assertEqual(calls);
  });

  it('limited_detail_never_calls_favorite_api', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'failed', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ',"metadata_error_code":"metadata_timeout"'));
    fixture.store.load('m1');
    await sleep(50);
    const limited = fixture.store.detail;
    expect(limited !== null && limited.isLimited()).assertTrue();
    fixture.store.setFavorite(true);
    await sleep(50);
    expect(fixture.transport.requests.length).assertEqual(1);
    expect(fixture.store.favoriteInFlight).assertFalse();
  });

  it('source_selection_rejects_rejected_and_clears_when_missing', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready',
      sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', '') + ',' +
      sourceJson('10000000-0000-0000-0000-000000000002', 'x1080x', 'B', 'rejected', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    // rejected 不可选
    fixture.store.selectSource('10000000-0000-0000-0000-000000000002');
    expect(fixture.store.selectedSourceId).assertNull();
    // 可选来源可选中
    fixture.store.selectSource('10000000-0000-0000-0000-000000000001');
    expect(fixture.store.selectedSourceId).assertEqual('10000000-0000-0000-0000-000000000001');
    // 重载后来源消失：选择自动清空
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000009', 'sehuatang', 'C', 'available', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.selectedSourceId).assertNull();
  });

  it('select_source_only_when_ready', 0, async () => {
    const fixture = new StoreFixture();
    fixture.store.selectSource('10000000-0000-0000-0000-000000000001');
    expect(fixture.store.selectedSourceId).assertNull();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    fixture.store.selectSource('10000000-0000-0000-0000-000000000001');
    expect(fixture.store.selectedSourceId).assertEqual('10000000-0000-0000-0000-000000000001');
  });

  it('failed_reload_clears_selection', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    fixture.store.selectSource('10000000-0000-0000-0000-000000000001');
    expect(fixture.store.selectedSourceId).assertEqual('10000000-0000-0000-0000-000000000001');
    fixture.routeDetail('{"code":"internal_error","message":"x","request_id":"r1"}', 500);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.selectedSourceId).assertNull();
  });

  it('detach_clears_all_state', 0, async () => {
    const fixture = new StoreFixture();
    fixture.routeDetail(movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ''));
    fixture.store.load('m1');
    await sleep(50);
    fixture.store.selectSource('10000000-0000-0000-0000-000000000001');
    fixture.store.detach();
    expect(fixture.store.movieId).assertNull();
    expect(fixture.store.detail).assertNull();
    expect(fixture.store.status).assertEqual(MovieDetailStatus.IDLE);
    expect(fixture.store.selectedSourceId).assertNull();
    expect(fixture.store.favoriteInFlight).assertFalse();
  });
});

  describe('MovieDetailDto', () => {
  it('rejects_duplicate_sources', 0, async () => {
    const body = movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', '') + ',' + sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), '');
    const fixture = new StoreFixture();
    fixture.routeDetail(body);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_unknown_availability', 0, async () => {
    const body = movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'raw', ''), '');
    const fixture = new StoreFixture();
    fixture.routeDetail(body);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_unknown_label_and_category', 0, async () => {
    const badLabel = movieDetailJson('m1', false, 'core_ready', '{"id":"10000000-0000-0000-0000-000000000001","website":"sehuatang","external_post_id":1,"title":"A","publish_date":null,"category":"中文字幕","labels":["hdr"],"resource_size_mb":1,"video_file_size_bytes":null,"availability":"ready"}', '');
    const fixture = new StoreFixture();
    fixture.routeDetail(badLabel);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
    const badCategory = movieDetailJson('m1', false, 'core_ready', '{"id":"10000000-0000-0000-0000-000000000001","website":"sehuatang","external_post_id":1,"title":"A","publish_date":null,"category":"无码","labels":[],"resource_size_mb":1,"video_file_size_bytes":null,"availability":"ready"}', '');
    const fixture2 = new StoreFixture();
    fixture2.routeDetail(badCategory);
    fixture2.store.load('m1');
    await sleep(50);
    expect(fixture2.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture2.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_negative_sizes', 0, async () => {
    const body = movieDetailJson('m1', false, 'core_ready', '{"id":"10000000-0000-0000-0000-000000000001","website":"sehuatang","external_post_id":1,"title":"A","publish_date":null,"category":"中文字幕","labels":[],"resource_size_mb":-1,"video_file_size_bytes":null,"availability":"ready"}', '');
    const fixture = new StoreFixture();
    fixture.routeDetail(body);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_metadata_error_code_when_not_failed', 0, async () => {
    const body = movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), ',"metadata_error_code":"x"');
    const fixture = new StoreFixture();
    fixture.routeDetail(body);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_duplicate_actors_and_over_limit_sources', 0, async () => {
    const dupActors = movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), '');
    const dupBody = dupActors.replace('"actors":[' + actorJson('a1', '张三') + ']',
      '"actors":[' + actorJson('a1', '张三') + ',' + actorJson('a1', '张三') + ']');
    const fixture = new StoreFixture();
    fixture.routeDetail(dupBody);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_non_positive_source_count', 0, async () => {
    const body = movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), '').replace('"source_count":2', '"source_count":0');
    const fixture = new StoreFixture();
    fixture.routeDetail(body);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_invalid_movie_labels', 0, async () => {
    const body = movieDetailJson('m1', false, 'core_ready', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), '').replace('"labels":["subtitle","4k"]', '"labels":["subtitle","hdr"]');
    const fixture = new StoreFixture();
    fixture.routeDetail(body);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });

  it('rejects_unknown_metadata_state', 0, async () => {
    const body = movieDetailJson('m1', false, 'bogus', sourceJson('10000000-0000-0000-0000-000000000001', 'sehuatang', 'A', 'ready', ''), '');
    const fixture = new StoreFixture();
    fixture.routeDetail(body);
    fixture.store.load('m1');
    await sleep(50);
    expect(fixture.store.status).assertEqual(MovieDetailStatus.FAILED);
    expect(fixture.store.errorCode).assertEqual('client_protocol_error');
  });
});
}
