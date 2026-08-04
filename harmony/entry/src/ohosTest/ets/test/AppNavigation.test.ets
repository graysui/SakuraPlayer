/**
 * TASK-303 测试：搜索分组/pending 自动刷新、快照队列计数、三 Tab 导航与顶部入口。
 *
 * JsUnit 部分用 FakeHttpTransport 驱动 SearchStore/SnapshotStore；
 * UiTest 部分通过 AuthStore 测试注入伪造认证，进入 AppNavigation 验证 UI。
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import { Driver, ON } from '@ohos.UiTest';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { SecureSessionStore, SecretStore } from '../../../main/ets/core/auth/SecureSessionStore';
import { authStore } from '../../../main/ets/core/auth/AuthStore';
import { SnapshotStore } from '../../../main/ets/core/events/SnapshotStore';
import { SearchStore, searchStore, SearchStatus } from '../../../main/ets/features/search/SearchStore';
import { ServerProfileStore } from '../../../main/ets/core/api/ServerProfile';
import { common } from '@kit.AbilityKit';

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

  static tokenBody(): string {
    return '{"access_token":"acc","refresh_token":"ref","token_type":"Bearer",' +
      '"access_expires_at":"2026-08-05T00:00:00Z","refresh_expires_at":"2026-09-03T00:00:00Z"}';
  }

  static bootstrapBody(initialized: boolean): string {
    return `{"initialized":${initialized},"api_version":1}`;
  }

  static snapshotBody(queued: number, running: number, ready: number): string {
    return `{"snapshot_version":5,"last_event_id":"c1",` +
      `"queues":{"metadata_queued":0,"metadata_running":0,"metadata_paused":false,` +
      `"cache_queued":${queued},"cache_running":${running},"cache_ready":${ready}},` +
      `"cache_jobs":[],"metadata_jobs":[],` +
      `"cloud115_binding":{"status":"unbound"},"notifications":[]}`;
  }

  static searchBody(pending: boolean): string {
    // 契约要求 pending_metadata 恒存在（可为空数组）
    const pendingJson = pending
      ? ',"pending_metadata":[{"movie_id":"m9","number":"ABC-999","state":"running","metadata_job_id":"j9"}]'
      : ',"pending_metadata":[]';
    return `{"movies":[{"id":"m1","number":"ABC-123","title":"示例影片","title_original":null,` +
      `"cover_url":null,"publish_date":null,"labels":[],"favorite":false,"source_count":1}],` +
      `"actors":[{"id":"a1","display_name":"示例女优","name_ja":null,"name_zh":null,` +
      `"aliases":[],"profile_url":null,"favorite":false}]${pendingJson}}`;
  }
}

export default function appNavigationTest() {
  describe('SearchStoreTest', () => {
    it('empty_query_is_idle', 0, async (done: Function) => {
      const store = new SearchStore();
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      store.attach(client, null);
      store.updateQuery('');
      expect(store.status).assertEqual(SearchStatus.IDLE);
      store.detach();
      done();
    });

    it('successful_search_groups_results', 0, async (done: Function) => {
      const store = new SearchStore();
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.searchBody(true)));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      store.attach(client, null);

      store.updateQuery('abc');
      await new Promise<void>((resolve) => setTimeout(resolve, 400));
      expect(store.status).assertEqual(SearchStatus.READY);
      expect(store.movies.length).assertEqual(1);
      expect(store.movies[0].number).assertEqual('ABC-123');
      expect(store.actors.length).assertEqual(1);
      expect(store.actors[0].displayName).assertEqual('示例女优');
      expect(store.pending.length).assertEqual(1);
      expect(store.pending[0].state).assertEqual('running');
      store.detach();
      done();
    });

    it('failed_search_sets_failed_status', 0, async (done: Function) => {
      const store = new SearchStore();
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(401, '{"code":"authentication_required","message":"expired","request_id":"r"}'));
      transport.responses.push(new QueuedResponse(401, '{"code":"refresh_token_invalid","message":"bad refresh","request_id":"r2"}'));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      store.attach(client, null);

      store.updateQuery('zzz');
      await new Promise<void>((resolve) => setTimeout(resolve, 400));
      expect(store.status).assertEqual(SearchStatus.FAILED);
      store.detach();
      done();
    });

    it('snapshot_change_auto_refreshes_pending', 0, async (done: Function) => {
      const store = new SearchStore();
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      // 队列：首次搜索 → 补全后 recover 快照 → 自动重查结果
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.searchBody(true)));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      const snapshot = new SnapshotStore(client);
      store.attach(client, snapshot);

      store.updateQuery('abc');
      await new Promise<void>((resolve) => setTimeout(resolve, 400));
      expect(store.pending.length).assertEqual(1);

      // 补全完成事件触发 recover → snapshot 变化 → SearchStore 重查（无 pending）
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(0, 0, 0)));
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.searchBody(false)));
      await snapshot.recover();
      await new Promise<void>((resolve) => setTimeout(resolve, 400));
      expect(store.pending.length).assertEqual(0);
      expect(store.movies.length).assertEqual(1);
      store.detach();
      done();
    });
  });

  describe('SnapshotQueuesTest', () => {
    it('recover_exposes_queue_counts', 0, async (done: Function) => {
      const session = new SecureSessionStore(new FakeSecretStore());
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(3, 1, 10)));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);
      const snapshot = new SnapshotStore(client);
      await snapshot.recover();
      expect(snapshot.queues != null).assertTrue();
      expect(snapshot.queues!.cacheQueued).assertEqual(3);
      expect(snapshot.queues!.cacheRunning).assertEqual(1);
      expect(snapshot.queues!.cacheReady).assertEqual(10);
      done();
    });
  });

  describe('AppNavigationUiTest', () => {
    let uiTestSkipped: boolean = false;

    beforeAll(async (done: Function) => {
      const appContext = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      // 安全门禁：设备已有真实服务器配置或真实会话时跳过 UiTest，
      // 避免测试注入破坏真实数据（TASK-303 审计 P1-1/P1-2/P1-4）。
      const savedBase = await ServerProfileStore.load(appContext);
      const hasRealSession = await authStore.hasStoredRefreshToken();
      if (savedBase !== null || hasRealSession) {
        uiTestSkipped = true;
        done();
        return;
      }
      // 干净设备：注入 Fake 传输，驱动到认证态
      const fake = new FakeHttpTransport();
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.bootstrapBody(true)));
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.tokenBody()));
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody(0, 1, 10)));
      authStore.setTransportForTesting(fake);
      await authStore.initialize(appContext);
      await authStore.configureServer('http://127.0.0.1:8000');
      await authStore.submitLogin('admin', 'pw');
      // 等待 Index 切换到 AppNavigation
      await new Promise<void>((resolve) => setTimeout(resolve, 1500));
      done();
    });

    afterAll(async (done: Function) => {
      if (!uiTestSkipped) {
        await authStore.logout();
        // 仅清理测试写入的基址（干净设备场景）
        await ServerProfileStore.clear(AbilityDelegatorRegistry.getAbilityDelegator().getAppContext());
        authStore.setTransportForTesting(null);
      }
      done();
    });

    it('three_tabs_visible', 0, async (done: Function) => {
      const driver = Driver.create();
      const library = await driver.findComponent(ON.text('媒体库'));
      expect(library != null).assertTrue();
      const rankings = await driver.findComponent(ON.text('排行榜'));
      expect(rankings != null).assertTrue();
      const actors = await driver.findComponent(ON.text('女优'));
      expect(actors != null).assertTrue();
      done();
    });

    it('top_entries_visible', 0, async (done: Function) => {
      const driver = Driver.create();
      const search = await driver.findComponent(ON.text('搜索'));
      expect(search != null).assertTrue();
      const settings = await driver.findComponent(ON.text('设置'));
      expect(settings != null).assertTrue();
      done();
    });

    it('cache_badge_shows_ready_count', 0, async (done: Function) => {
      const driver = Driver.create();
      const ready = await driver.findComponent(ON.text('10'));
      expect(ready != null).assertTrue();
      done();
    });

    it('settings_push_and_back', 0, async (done: Function) => {
      const driver = Driver.create();
      // 坐标点击顶部栏"设置"（UiTest 组件 click 偶发未命中）
      const settings = await driver.findComponent(ON.text('设置'));
      const bounds = await settings.getBounds();
      const cx = Math.floor((bounds.left + bounds.right) / 2);
      const cy = Math.floor((bounds.top + bounds.bottom) / 2);
      await driver.click(cx, cy);
      await new Promise<void>((resolve) => setTimeout(resolve, 1500));
      const placeholder = await driver.findComponent(ON.id('settings_placeholder'));
      expect(placeholder != null).assertTrue();
      await driver.pressBack();
      await new Promise<void>((resolve) => setTimeout(resolve, 1200));
      const library = await driver.findComponent(ON.text('媒体库'));
      expect(library != null).assertTrue();
      done();
    });
  });
}
