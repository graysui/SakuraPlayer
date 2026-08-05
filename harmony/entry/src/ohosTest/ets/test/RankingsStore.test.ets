/**
 * TASK-305 排行榜状态测试：
 * - 查询参数构造（board/year/limit/cursor）
 * - 四榜单切换、TOP250 年份可见性与可用年份约束
 * - rank 间隙保留、synced_at 保留、available_years 降序校验
 * - 刷新失败保留列表；追加失败保留并重试；cursor 失效重载第一页
 * - 503 ranking_snapshot_unavailable 区分；真实空态 vs 不可用
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { TokenPair } from '../../../main/ets/core/api/ApiModels';
import { RankingsStore, RankingsStatus } from '../../../main/ets/features/rankings/RankingsStore';

const SYNCED_AT = '2026-08-04T12:00:00Z';

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

function rankingItemBody(rank: number, id: string, number: string): string {
  return `{"rank":${rank},"movie":{"id":"${id}","number":"${number}","title":"标题 ${number}",` +
    `"title_original":null,"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],` +
    `"favorite":false,"source_count":1,"progress":null}}`;
}

function rankingBody(board: string, year: number | null, availableYears: number[],
  items: string, nextCursor: string | null): string {
  const yearsJson = availableYears.length === 0 ? '[]' : `[${availableYears.join(',')}]`;
  return `{"board":"${board}","year":${year === null ? 'null' : year},` +
    `"available_years":${yearsJson},"synced_at":"${SYNCED_AT}",` +
    `"items":${items},"next_cursor":${nextCursor === null ? 'null' : `"${nextCursor}"`}}`;
}

function unavailableBody(reason: string): string {
  return `{"code":"ranking_snapshot_unavailable","message":"no snapshot",` +
    `"request_id":"r1","details":{"reason":"${reason}"}}`;
}

class StoreFixture {
  store: RankingsStore;
  transport: FakeHttpTransport;

  constructor(store: RankingsStore, transport: FakeHttpTransport) {
    this.store = store;
    this.transport = transport;
  }
}

function makeStore(): StoreFixture {
  const transport = new FakeHttpTransport();
  const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', new FakeSession());
  const store = new RankingsStore();
  store.attach(client);
  return new StoreFixture(store, transport);
}

export default function rankingsStoreTest() {
  describe('RankingsStoreTest', () => {

    it('daily_board_query_has_no_year', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.refresh();
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.READY);
      expect(store.items.length).assertEqual(1);
      const url = transport.requests[transport.requests.length - 1].url;
      expect(url).assertContain('/rankings?');
      expect(url).assertContain('board=daily');
      expect(url).assertContain('limit=24');
      expect(url.includes('year=')).assertFalse();
    });

    it('top250_without_year_is_overall_board', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', null, [2026, 2025],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.selectBoard('top250');
      await sleep(50);
      const url = transport.requests[transport.requests.length - 1].url;
      expect(url).assertContain('board=top250');
      expect(url.includes('year=')).assertFalse();
      expect(store.availableYears.length).assertEqual(2);
    });

    it('top250_year_sends_year_and_is_limited_to_available', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', null, [2026, 2025],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.selectBoard('top250');
      await sleep(50);
      expect(transport.requests.length).assertEqual(1);

      // 未声明年份被拒绝（不发起请求）
      store.selectYear(2010);
      await sleep(50);
      expect(transport.requests.length).assertEqual(1);

      // 服务端声明年份可用
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', 2025, [2026, 2025],
        `[${rankingItemBody(2, 'a2', 'ABC-002')}]`, null)));
      store.selectYear(2025);
      await sleep(50);
      expect(store.year).assertEqual(2025);
      const url = transport.requests[transport.requests.length - 1].url;
      expect(url).assertContain('year=2025');
    });

    it('switching_board_clears_year', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', null, [2026, 2025],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.selectBoard('top250');
      await sleep(50);
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', 2025, [2026, 2025],
        `[${rankingItemBody(2, 'a2', 'ABC-002')}]`, null)));
      store.selectYear(2025);
      await sleep(50);
      expect(store.year).assertEqual(2025);

      // 切换到周榜清空 year
      transport.responses.push(new QueuedResponse(200, rankingBody('weekly', null, [],
        `[${rankingItemBody(3, 'a3', 'ABC-003')}]`, null)));
      store.selectBoard('weekly');
      await sleep(50);
      expect(store.board).assertEqual('weekly');
      expect(store.year).assertNull();
      const url = transport.requests[transport.requests.length - 1].url;
      expect(url).assertContain('board=weekly');
      expect(url.includes('year=')).assertFalse();
    });

    it('rank_gaps_and_synced_at_preserved', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      const items = `[${rankingItemBody(1, 'a1', 'ABC-001')},${rankingItemBody(3, 'a2', 'ABC-002')},` +
        `${rankingItemBody(7, 'a3', 'ABC-003')}]`;
      transport.responses.push(new QueuedResponse(200, rankingBody('monthly', null, [], items, null)));
      store.selectBoard('monthly');
      await sleep(50);
      expect(store.items.length).assertEqual(3);
      expect(store.items[0].rank).assertEqual(1);
      expect(store.items[1].rank).assertEqual(3);
      expect(store.items[2].rank).assertEqual(7);
      expect(store.syncedAt).assertEqual(SYNCED_AT);
    });

    it('non_descending_available_years_is_protocol_error', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', null, [2025, 2026],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.selectBoard('top250');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.FAILED);
    });

    it('refresh_failure_keeps_items_cursor_and_synced_at', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, 'c1')));
      store.refresh();
      await sleep(50);
      expect(store.hasMore).assertTrue();

      transport.responses.push(new QueuedResponse(500, '{"code":"internal_error","message":"boom","request_id":"r1"}'));
      store.refresh();
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.READY);
      expect(store.items.length).assertEqual(1);
      expect(store.hasMore).assertTrue();
      expect(store.syncedAt).assertEqual(SYNCED_AT);
      expect(store.errorMessage != null).assertTrue();
    });

    it('append_failure_keeps_items_and_retry_succeeds', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, 'c1')));
      store.refresh();
      await sleep(50);
      transport.responses.push(new QueuedResponse(500, '{"code":"internal_error","message":"boom","request_id":"r1"}'));
      store.loadMore();
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.APPEND_FAILED);
      expect(store.items.length).assertEqual(1);
      expect(store.hasMore).assertTrue();

      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [],
        `[${rankingItemBody(2, 'b2', 'ABC-002')}]`, null)));
      store.retryAppend();
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.READY);
      expect(store.items.length).assertEqual(2);
      expect(store.items[1].rank).assertEqual(2);
      expect(store.hasMore).assertFalse();
    });

    it('cursor_invalidation_reloads_first_page_on_422', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, 'c1')));
      store.refresh();
      await sleep(50);

      transport.responses.push(new QueuedResponse(422, '{"code":"validation_failed","message":"cursor expired","request_id":"r1"}'));
      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [],
        `[${rankingItemBody(5, 'r1', 'ABC-999')}]`, 'c9')));
      store.loadMore();
      await waitUntil(() => transport.requests.length >= 3, 2000);
      expect(store.status).assertEqual(RankingsStatus.READY);
      const lastUrl = transport.requests[transport.requests.length - 1].url;
      expect(lastUrl.includes('cursor=')).assertFalse();
      expect(store.items.length).assertEqual(1);
      expect(store.items[0].rank).assertEqual(5);
    });

    it('unavailable_credentials_not_configured', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(503, unavailableBody('credentials_not_configured')));
      store.selectBoard('top250');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.UNAVAILABLE);
      expect(store.unavailableReason).assertEqual('credentials_not_configured');
      expect(store.items.length).assertEqual(0);
    });

    it('empty_snapshot_is_real_empty_not_unavailable', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('weekly', null, [], '[]', null)));
      store.selectBoard('weekly');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.READY);
      expect(store.items.length).assertEqual(0);
      expect(store.unavailableReason).assertNull();
    });

    it('unknown_unavailable_reason_is_failed', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(503, unavailableBody('mystery_reason')));
      store.selectBoard('daily');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.FAILED);
      expect(store.unavailableReason).assertNull();
    });

    it('one_board_unavailable_does_not_affect_other_boards', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(503, unavailableBody('never_synced')));
      store.selectBoard('daily');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.UNAVAILABLE);
      expect(store.unavailableReason).assertEqual('never_synced');

      transport.responses.push(new QueuedResponse(200, rankingBody('monthly', null, [],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.selectBoard('monthly');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.READY);
      expect(store.items.length).assertEqual(1);
    });

    it('switching_board_clears_previous_items', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.selectBoard('daily');
      await sleep(50);
      expect(store.items.length).assertEqual(1);

      // 切换到周榜：items 立即清空（LOADING 期间不得显示其他榜单旧数据）
      transport.responses.push(new QueuedResponse(200, rankingBody('weekly', null, [],
        `[${rankingItemBody(2, 'b2', 'ABC-002')}]`, null)));
      store.selectBoard('weekly');
      expect(store.items.length).assertEqual(0);
      expect(store.status).assertEqual(RankingsStatus.LOADING);
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.READY);
      expect(store.board).assertEqual('weekly');
      expect(store.items.length).assertEqual(1);
    });

    it('unavailable_requires_http_503', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      // 非 503 的 ranking_snapshot_unavailable code 不进入不可用状态
      transport.responses.push(new QueuedResponse(500, unavailableBody('credentials_not_configured')));
      store.selectBoard('daily');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.FAILED);
      expect(store.unavailableReason).assertNull();
    });

    it('unavailable_without_details_is_failed', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(503,
        '{"code":"ranking_snapshot_unavailable","message":"no snapshot","request_id":"r1"}'));
      store.selectBoard('daily');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.FAILED);
      expect(store.unavailableReason).assertNull();
    });

    it('oversized_items_page_is_protocol_error', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      // 101 条（契约 maxItems 100）
      let items = '';
      for (let i = 1; i <= 101; i++) {
        if (i > 1) {
          items += ',';
        }
        items += rankingItemBody(i, `id${i}`, `N-${i}`);
      }
      transport.responses.push(new QueuedResponse(200, rankingBody('daily', null, [], `[${items}]`, null)));
      store.selectBoard('daily');
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.FAILED);
    });

    it('refresh_drops_year_not_in_available_years', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', null, [2026, 2025],
        `[${rankingItemBody(1, 'a1', 'ABC-001')}]`, null)));
      store.selectBoard('top250');
      await sleep(50);
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', 2025, [2026, 2025],
        `[${rankingItemBody(2, 'a2', 'ABC-002')}]`, null)));
      store.selectYear(2025);
      await sleep(50);
      expect(store.year).assertEqual(2025);

      // 刷新后服务端只声明 2026：year 回落总榜，Select 不显示陈旧年份
      transport.responses.push(new QueuedResponse(200, rankingBody('top250', null, [2026],
        `[${rankingItemBody(3, 'a3', 'ABC-003')}]`, null)));
      store.refresh();
      await sleep(50);
      expect(store.status).assertEqual(RankingsStatus.READY);
      expect(store.year).assertNull();
      expect(store.availableYears.length).assertEqual(1);
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
