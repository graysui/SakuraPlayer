/**
 * TASK-304 媒体库状态测试：
 * - 查询参数构造（分类/标签/来源/可播放/大小/排序/收藏）
 * - 游标分页、按 movie ID 去重
 * - 追加失败保留数据并可重试
 * - 游标失效（validation_failed）清游标重载第一页
 * - 收藏切换触发刷新
 */

import { describe, it, expect, beforeEach } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { TokenPair } from '../../../main/ets/core/api/ApiModels';
import { SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { LibraryStore, LibraryStatus } from '../../../main/ets/features/library/LibraryStore';

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
  requests: HttpRequest[] = [];

  request(request: HttpRequest): Promise<HttpResponse> {
    this.requests.push(request);
    const next = this.responses.length > 0 ? this.responses.shift() : undefined;
    if (next === undefined) {
      return Promise.reject(new Error('no queued response'));
    }
    const response: HttpResponse = { statusCode: next.status, body: next.body };
    return Promise.resolve(response);
  }
}

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

function movieBody(id: string, number: string, nextCursor: string | null, progress: string | null): string {
  const progressJson = progress !== null ? `,"progress":${progress}` : ',"progress":null';
  return `{"items":[{"id":"${id}","number":"${number}","title":"标题 ${number}","title_original":null,` +
    `"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,"source_count":1${progressJson}}],` +
    `"next_cursor":${nextCursor === null ? 'null' : `"${nextCursor}"`}}`;
}

class StoreFixture {
  store: LibraryStore;
  transport: FakeHttpTransport;

  constructor(store: LibraryStore, transport: FakeHttpTransport) {
    this.store = store;
    this.transport = transport;
  }
}

function makeStore(): StoreFixture {
  const transport = new FakeHttpTransport();
  const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', new FakeSession());
  const store = new LibraryStore();
  store.attach(client);
  return new StoreFixture(store, transport);
}

export default function libraryStoreTest() {
  describe('LibraryStoreTest', () => {
  it('builds_movies_query_with_combined_filters', 0, async () => {
    const fixture = makeStore();
    const store = fixture.store;
    const transport = fixture.transport;
    transport.responses.push(new QueuedResponse(200, movieBody('a1', 'ABC-001', null, null)));
    store.categories = ['亚洲有码', '中文字幕'];
    store.labels = ['subtitle', '4k'];
    store.sourceWebsite = 'sehuatang';
    store.playable = true;
    store.minSizeMb = 100;
    store.maxSizeMb = 5000;
    store.sort = 'number_asc';
    store.favorite = true;
    store.refresh();
    await sleep(50);
    expect(store.status).assertEqual(LibraryStatus.READY);
    expect(store.items.length).assertEqual(1);
    const url = transport.requests[transport.requests.length - 1].url;
    expect(url).assertContain('/movies?');
    expect(url).assertContain('limit=24');
    expect(url).assertContain('categories=' + encodeURIComponent('亚洲有码,中文字幕'));
    expect(url).assertContain('labels=' + encodeURIComponent('subtitle,4k'));
    expect(url).assertContain('source_website=sehuatang');
    expect(url).assertContain('playable=true');
    expect(url).assertContain('min_resource_size_mb=100');
    expect(url).assertContain('max_resource_size_mb=5000');
    expect(url).assertContain('sort=number_asc');
    expect(url).assertContain('favorite=true');
  });

  it('defaults_to_publish_date_desc_without_favorite', 0, async () => {
    const fixture = makeStore();
    const store = fixture.store;
    const transport = fixture.transport;
    transport.responses.push(new QueuedResponse(200, movieBody('a1', 'ABC-001', null, null)));
    store.refresh();
    await sleep(50);
    const url = transport.requests[transport.requests.length - 1].url;
    expect(url).assertContain('sort=publish_date_desc');
    expect(url.includes('favorite')).assertFalse();
  });

  it('appends_pages_and_deduplicates_by_movie_id', 0, async () => {
    const fixture = makeStore();
    const store = fixture.store;
    const transport = fixture.transport;
    transport.responses.push(new QueuedResponse(200, movieBody('a1', 'ABC-001', 'c1', null)));
    store.refresh();
    await sleep(50);
    expect(store.items.length).assertEqual(1);

    // 第二页含重复 id a1 与新 id b2（游标分页重叠）
    const second = '{"items":[' +
      '{"id":"a1","number":"ABC-001","title":"标题 ABC-001","title_original":null,"cover_url":null,' +
      '"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,"source_count":1,"progress":null},' +
      '{"id":"b2","number":"ABC-002","title":"标题 ABC-002","title_original":null,"cover_url":null,' +
      '"publish_date":"2026-01-02","labels":[],"favorite":false,"source_count":1,"progress":null}],' +
      '"next_cursor":null}';
    transport.responses.push(new QueuedResponse(200, second));
    store.loadMore();
    await sleep(50);
    expect(store.status).assertEqual(LibraryStatus.READY);
    expect(store.items.length).assertEqual(2);
    expect(store.hasMore).assertFalse();
  });

  it('append_failure_keeps_items_and_retry_succeeds', 0, async () => {
    const fixture = makeStore();
    const store = fixture.store;
    const transport = fixture.transport;
    transport.responses.push(new QueuedResponse(200, movieBody('a1', 'ABC-001', 'c1', null)));
    store.refresh();
    await sleep(50);
    transport.responses.push(new QueuedResponse(500, '{"code":"internal_error","message":"boom","request_id":"r1"}'));
    store.loadMore();
    await sleep(50);
    expect(store.status).assertEqual(LibraryStatus.APPEND_FAILED);
    expect(store.items.length).assertEqual(1);

    transport.responses.push(new QueuedResponse(200, movieBody('b2', 'ABC-002', null, null)));
    store.retryAppend();
    await sleep(50);
    expect(store.status).assertEqual(LibraryStatus.READY);
    expect(store.items.length).assertEqual(2);
  });

  it('cursor_invalidation_reloads_first_page_on_422', 0, async () => {
    const fixture = makeStore();
    const store = fixture.store;
    const transport = fixture.transport;
    transport.responses.push(new QueuedResponse(200, movieBody('a1', 'ABC-001', 'c1', null)));
    store.refresh();
    await sleep(50);
    expect(store.hasMore).assertTrue();

    // 追加返回 422 validation_failed（游标跨查询/失效）→ 清游标重载第一页
    transport.responses.push(new QueuedResponse(422, '{"code":"validation_failed","message":"cursor expired","request_id":"r1"}'));
    transport.responses.push(new QueuedResponse(200, movieBody('r1', 'ABC-999', 'c9', null)));
    store.loadMore();
    await waitUntil(() => transport.requests.length >= 3, 2000);
    expect(store.status).assertEqual(LibraryStatus.READY);
    const lastUrl = transport.requests[transport.requests.length - 1].url;
    expect(lastUrl.includes('cursor=')).assertFalse();
  });

  it('toggle_favorite_triggers_refresh', 0, async () => {
    const fixture = makeStore();
    const store = fixture.store;
    const transport = fixture.transport;
    transport.responses.push(new QueuedResponse(200, movieBody('a1', 'ABC-001', null, null)));
    store.refresh();
    await sleep(50);
    expect(transport.requests.length).assertEqual(1);
    store.toggleFavorite();
    await sleep(50);
    expect(transport.requests.length).assertEqual(2);
    const url = transport.requests[transport.requests.length - 1].url;
    expect(url).assertContain('favorite=true');
  });

  it('parses_progress_and_completed_state', 0, async () => {
    const fixture = makeStore();
    const store = fixture.store;
    const transport = fixture.transport;
    const progress = '{"position_seconds":300,"duration_seconds":1000,"completed":false,"version":1}';
    transport.responses.push(new QueuedResponse(200, movieBody('a1', 'ABC-001', null, progress)));
    store.refresh();
    await sleep(50);
    const progressObj = store.items[0].progress;
    if (progressObj === null) {
      expect(false).assertTrue();
      return;
    }
    const fraction = progressObj.fraction();
    expect(fraction).assertClose(0.3, 0.01);
  });
});
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function waitUntil(condition: () => boolean, timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const tick = (): void => {
      if (condition() || Date.now() >= deadline) {
        resolve();
        return;
      }
      setTimeout(tick, 20);
    };
    tick();
  });
}
