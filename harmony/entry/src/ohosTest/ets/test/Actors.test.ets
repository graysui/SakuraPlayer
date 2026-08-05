/**
 * TASK-306 女优列表/详情测试：
 * - 查询参数（q 去空白/limit/favorite）、300ms 防抖、Enter 立即提交
 * - 切换 scope 清空旧内容、追加失败保留、cursor 422 恢复
 * - 收藏在途防重、成功同步列表、favorite 模式取消收藏移除项、失败保留旧值
 * - 详情加载/generation/收藏双向同步、detach 清空
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { TokenPair } from '../../../main/ets/core/api/ApiModels';
import {
  ActorDetailStatus, ActorDetailStore, ActorsStatus, ActorsStore,
} from '../../../main/ets/features/actors/ActorsStore';

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

function actorItem(id: string, displayName: string, favorite: boolean): string {
  return `{"id":"${id}","display_name":"${displayName}","name_ja":"${displayName}","name_zh":null,` +
    `"aliases":["${displayName}别名"],"profile_url":null,"favorite":${favorite}}`;
}

function actorPage(items: string, nextCursor: string | null): string {
  return `{"items":[${items}],"next_cursor":${nextCursor === null ? 'null' : `"${nextCursor}"`}}`;
}

function actorDetail(id: string, displayName: string, favorite: boolean, bio: string | null,
  galleryCount: number): string {
  const gallery = galleryCount > 0
    ? '["https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/A/a1.jpg"]'
    : '[]';
  return `{"id":"${id}","display_name":"${displayName}","name_ja":"${displayName}","name_zh":null,` +
    `"aliases":["${displayName}别名"],"profile_url":null,"favorite":${favorite},` +
    `"bio":${bio === null ? 'null' : `"${bio}"`},"bio_original":null,` +
    `"gallery_urls":${gallery},"movies":[]}`;
}

class StoreFixture {
  store: ActorsStore;
  transport: FakeHttpTransport;

  constructor(store: ActorsStore, transport: FakeHttpTransport) {
    this.store = store;
    this.transport = transport;
  }
}

function makeStore(): StoreFixture {
  const transport = new FakeHttpTransport();
  const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', new FakeSession());
  const store = new ActorsStore();
  store.attach(client);
  return new StoreFixture(store, transport);
}

function makeDetailStore(onFavoriteSynced: (actorId: string, enabled: boolean) => void): ActorDetailStore {
  const transport = new FakeHttpTransport();
  const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', new FakeSession());
  const store = new ActorDetailStore(onFavoriteSynced);
  store.attach(client);
  return store;
}

export default function actorsTest() {
  describe('ActorsStoreTest', () => {
    it('query_trims_whitespace_and_builds_params', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      store.setQuery('  张三  ');
      store.submitQuery();
      await sleep(50);
      expect(store.status).assertEqual(ActorsStatus.READY);
      const url = transport.requests[transport.requests.length - 1].url;
      expect(url).assertContain('/actors?');
      expect(url).assertContain(`q=${encodeURIComponent('张三')}`);
      expect(url).assertContain('limit=24');
      expect(url.includes('favorite=')).assertFalse();
    });

    it('favorite_mode_sends_favorite_true', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', true), null)));
      store.toggleFavoriteMode();
      await sleep(50);
      expect(store.favoriteMode).assertTrue();
      const url = transport.requests[transport.requests.length - 1].url;
      expect(url).assertContain('favorite=true');
    });

    it('debounce_delays_query_until_300ms', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      store.setQuery('李四');
      await sleep(100);
      expect(transport.requests.length).assertEqual(0);
      await sleep(300);
      expect(transport.requests.length).assertEqual(1);
      expect(store.activeQuery).assertEqual('李四');
    });

    it('switching_scope_clears_previous_items', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      store.refresh();
      await sleep(50);
      expect(store.items.length).assertEqual(1);

      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('b2', '李四', false), null)));
      store.setQuery('李四');
      store.submitQuery();
      expect(store.items.length).assertEqual(0);
      expect(store.status).assertEqual(ActorsStatus.LOADING);
      await sleep(50);
      expect(store.items.length).assertEqual(1);
      expect(store.items[0].id).assertEqual('b2');
    });

    it('append_failure_keeps_items_and_retry', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), 'c1')));
      store.refresh();
      await sleep(50);
      transport.responses.push(new QueuedResponse(500, '{"code":"internal_error","message":"boom","request_id":"r1"}'));
      store.loadMore();
      await sleep(50);
      expect(store.status).assertEqual(ActorsStatus.APPEND_FAILED);
      expect(store.items.length).assertEqual(1);
      expect(store.hasMore).assertTrue();

      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('b2', '李四', false), null)));
      store.retryAppend();
      await sleep(50);
      expect(store.status).assertEqual(ActorsStatus.READY);
      expect(store.items.length).assertEqual(2);
    });

    it('cursor_invalidation_reloads_first_page_on_422', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), 'c1')));
      store.refresh();
      await sleep(50);
      transport.responses.push(new QueuedResponse(422, '{"code":"validation_failed","message":"cursor expired","request_id":"r1"}'));
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('r1', '恢复', false), 'c9')));
      store.loadMore();
      await waitUntil(() => transport.requests.length >= 3, 2000);
      expect(store.status).assertEqual(ActorsStatus.READY);
      expect(store.items.length).assertEqual(1);
      expect(store.items[0].id).assertEqual('r1');
    });

    it('set_favorite_updates_list_item', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      store.refresh();
      await sleep(50);
      transport.responses.push(new QueuedResponse(204, ''));
      store.setFavorite('a1', true);
      await sleep(50);
      expect(store.isFavoriteInFlight('a1')).assertFalse();
      expect(store.items[0].favorite).assertTrue();
      const lastUrl = transport.requests[transport.requests.length - 1].url;
      expect(lastUrl).assertContain('/actors/a1/favorite');
    });

    it('set_favorite_ignores_duplicate_in_flight', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      store.refresh();
      await sleep(50);
      transport.responses.push(new QueuedResponse(204, ''));
      transport.responses.push(new QueuedResponse(204, ''));
      store.setFavorite('a1', true);
      store.setFavorite('a1', true); // 在途：忽略
      await sleep(50);
      // 只有一次收藏请求
      const favorites = transport.requests.filter((r: HttpRequest) => r.url.includes('/favorite'));
      expect(favorites.length).assertEqual(1);
    });

    it('favorite_mode_unfavorite_removes_item', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', true), null)));
      store.toggleFavoriteMode();
      await sleep(50);
      expect(store.items.length).assertEqual(1);
      transport.responses.push(new QueuedResponse(204, ''));
      store.setFavorite('a1', false);
      await sleep(50);
      expect(store.items.length).assertEqual(0);
    });

    it('set_favorite_failure_keeps_old_value', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      store.refresh();
      await sleep(50);
      transport.responses.push(new QueuedResponse(500, '{"code":"internal_error","message":"boom","request_id":"r1"}'));
      store.setFavorite('a1', true);
      await sleep(50);
      expect(store.items[0].favorite).assertFalse();
      expect(store.favoriteErrorMessage != null).assertTrue();
    });

    it('detail_loads_and_syncs_favorite_to_list', 0, async () => {
      const listFixture = makeStore();
      const listStore = listFixture.store;
      const detailStore = makeDetailStore((actorId: string, enabled: boolean) => {
        listStore.acceptFavorite(actorId, enabled);
      });
      const listTransport = listFixture.transport;
      listTransport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      listStore.refresh();
      await sleep(50);
      detailStore.attach(new ApiClient(listTransport, 'http://127.0.0.1:8000/api/v1', new FakeSession()));
      listTransport.responses.push(new QueuedResponse(200, actorDetail('a1', '张三', false, '简介', 1)));
      detailStore.load('a1');
      await sleep(50);
      expect(detailStore.status).assertEqual(ActorDetailStatus.READY);
      expect(detailStore.detail != null).assertTrue();
      expect(detailStore.detail!.bio).assertEqual('简介');
      expect(detailStore.detail!.galleryUrls.length).assertEqual(1);

      listTransport.responses.push(new QueuedResponse(204, ''));
      detailStore.setFavorite(true);
      await sleep(50);
      expect(detailStore.detail!.summary.favorite).assertTrue();
      expect(listStore.items[0].favorite).assertTrue();
    });

    it('favorite_in_flight_does_not_pollute_new_scope', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', false), null)));
      store.refresh();
      await sleep(50);
      expect(store.items.length).assertEqual(1);
      // 收藏在途（响应挂起）期间切换 scope
      transport.responses.push(new QueuedResponse(204, ''));
      store.setFavorite('a1', true);
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('b2', '李四', true), null)));
      store.setQuery('李四');
      store.submitQuery();
      await sleep(50);
      expect(store.items.length).assertEqual(1);
      expect(store.items[0].id).assertEqual('b2');
      expect(store.items[0].favorite).assertTrue();
      // 旧收藏回调返回（gen 不匹配）：不得修改新 scope 列表
      transport.responses.shift();
      await sleep(100);
      expect(store.items.length).assertEqual(1);
      expect(store.items[0].id).assertEqual('b2');
    });

    it('detach_clears_all_state', 0, async () => {
      const fixture = makeStore();
      const store = fixture.store;
      const transport = fixture.transport;
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', true), 'c1')));
      transport.responses.push(new QueuedResponse(200, actorPage(actorItem('a1', '张三', true), null)));
      store.setQuery('张三');
      store.submitQuery();
      await sleep(50);
      store.toggleFavoriteMode();
      await sleep(50);
      expect(store.items.length).assertEqual(1);
      store.detach();
      expect(store.query).assertEqual('');
      expect(store.activeQuery).assertEqual('');
      expect(store.favoriteMode).assertFalse();
      expect(store.items.length).assertEqual(0);
      expect(store.status).assertEqual(ActorsStatus.IDLE);
      expect(store.hasMore).assertFalse();
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
