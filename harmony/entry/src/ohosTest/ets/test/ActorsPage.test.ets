/**
 * TASK-306 女优列表/详情 UiTest（真实运行时）。
 * 安全门禁：真实服务器配置或真实会话时跳过；干净设备注入 Fake 传输驱动认证态。
 * fixture 不包含真实 GFriends URL（profile_url/gallery_urls 为空），无真实网络访问。
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { Driver, ON } from '@ohos.UiTest';
import { HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { authStore } from '../../../main/ets/core/auth/AuthStore';
import { actorsStore } from '../../../main/ets/features/actors/ActorsStore';
import { ServerProfileStore } from '../../../main/ets/core/api/ServerProfile';

class QueuedResponse {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    this.status = status;
    this.body = body;
  }
}

class FakeHttpTransport implements HttpTransport {
  // 按 URL 子串路由（先插入者优先匹配），消除消费顺序依赖
  routes: Map<string, QueuedResponse> = new Map();

  async request(request: HttpRequest): Promise<HttpResponse> {
    for (const entry of this.routes) {
      if (request.url.includes(entry[0])) {
        const result: HttpResponse = { statusCode: entry[1].status, body: entry[1].body };
        return result;
      }
    }
    throw new Error(`no route for ${request.url}`);
  }

  static tokenBody(): string {
    return '{"access_token":"acc","refresh_token":"ref","token_type":"Bearer",' +
      '"access_expires_at":"2026-08-05T00:00:00Z","refresh_expires_at":"2026-09-03T00:00:00Z"}';
  }

  static bootstrapBody(initialized: boolean): string {
    return `{"initialized":${initialized},"api_version":1}`;
  }

  static snapshotBody(): string {
    return '{"snapshot_version":5,"last_event_id":"c1",' +
      '"queues":{"metadata_queued":0,"metadata_running":0,"metadata_paused":false,' +
      '"cache_queued":0,"cache_running":0,"cache_ready":0},' +
      '"cache_jobs":[],"metadata_jobs":[],' +
      '"cloud115_binding":{"bound":false,"status":"unbound","display_name":null,"cache_root_ready":false,"last_verified_at":null},"notifications":[]}';
  }

  static moviesBody(): string {
    return '{"items":[{"id":"m1","number":"ABC-001","title":"媒体库示例","title_original":null,' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,' +
      '"source_count":1,"progress":null}],"next_cursor":null}';
  }

  static actorItem(id: string, displayName: string, favorite: boolean): string {
    return `{"id":"${id}","display_name":"${displayName}","name_ja":"${displayName}","name_zh":null,` +
      `"aliases":["${displayName}别名"],"profile_url":null,"favorite":${favorite}}`;
  }

  static actorsBody(): string {
    return `{"items":[${FakeHttpTransport.actorItem('a1', '张三', false)},` +
      `${FakeHttpTransport.actorItem('a2', '李四', false)}],"next_cursor":null}`;
  }

  static detailBody(): string {
    return `{"id":"a1","display_name":"张三","name_ja":"张三","name_zh":null,` +
      `"aliases":["张三别名"],"profile_url":null,"favorite":false,` +
      `"bio":"知名女优简介","bio_original":null,"gallery_urls":[],` +
      `"movies":[{"id":"m1","number":"ABC-001","title":"媒体库示例","title_original":null,` +
      `"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,` +
      `"source_count":1,"progress":null}]}`;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function waitForText(text: string, timeoutMs: number): Promise<boolean> {
  const driver = Driver.create();
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const found = await driver.findComponent(ON.text(text));
    if (found !== null) {
      return true;
    }
    await sleep(300);
  }
  return false;
}

export default function actorsPageTest() {
  describe('ActorsPageTest', () => {
    let uiTestSkipped: boolean = false;

    beforeAll(async (done: Function) => {
      const appContext = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      const savedBase = await ServerProfileStore.load(appContext);
      const hasRealSession = await authStore.hasStoredRefreshToken();
      if (savedBase !== null || hasRealSession) {
        uiTestSkipped = true;
        done();
        return;
      }
      // 隔离跨套件状态
      actorsStore.detach();
      const fake = new FakeHttpTransport();
      // 按 URL 路由：认证、快照（WebSocket 重连 recover 可重复命中）、媒体库、女优
      fake.routes.set('/auth/bootstrap', new QueuedResponse(200, FakeHttpTransport.bootstrapBody(true)));
      fake.routes.set('/auth/login', new QueuedResponse(200, FakeHttpTransport.tokenBody()));
      fake.routes.set('/events/snapshot', new QueuedResponse(200, FakeHttpTransport.snapshotBody()));
      fake.routes.set('/movies', new QueuedResponse(200, FakeHttpTransport.moviesBody()));
      // favorite 路由先于详情路由插入（/actors/a1/favorite 优先匹配）
      fake.routes.set('/favorite', new QueuedResponse(204, ''));
      fake.routes.set('/actors/a1', new QueuedResponse(200, FakeHttpTransport.detailBody()));
      fake.routes.set('/actors', new QueuedResponse(200, FakeHttpTransport.actorsBody()));
      authStore.setTransportForTesting(fake);
      await authStore.initialize(appContext);
      await authStore.configureServer('http://127.0.0.1:8000');
      await authStore.submitLogin('admin', 'pw');
      await sleep(1500);
      done();
    });

    afterAll(async (done: Function) => {
      if (!uiTestSkipped) {
        await authStore.logout();
        await ServerProfileStore.clear(AbilityDelegatorRegistry.getAbilityDelegator().getAppContext());
        authStore.setTransportForTesting(null);
      }
      done();
    });

    it('actors_tab_renders_search_and_cards', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      const libraryReady = await waitForText('媒体库示例', 6000);
      expect('library ready=' + libraryReady).assertEqual('library ready=true');
      // 点击底部"女优" Tab（避开系统手势条，点击 tab 栏上部）
      const tab = await driver.findComponent(ON.text('女优'));
      expect(tab != null).assertTrue();
      if (tab === null) {
        done();
        return;
      }
      const bounds = await tab.getBounds();
      const cx = Math.floor((bounds.left + bounds.right) / 2);
      const cy = Math.max(0, bounds.top - 100);
      await driver.click(cx, cy);
      const cardVisible = await waitForText('张三', 6000);
      expect('actor card=' + cardVisible).assertEqual('actor card=true');
      const secondVisible = await waitForText('李四', 3000);
      expect('second card=' + secondVisible).assertEqual('second card=true');
      const favoriteVisible = await waitForText('☆', 3000);
      expect('favorite=' + favoriteVisible).assertEqual('favorite=true');
      done();
    });

    it('actor_detail_navigates_shows_sections_and_favorite', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      // 点击"张三"卡片进入详情
      const card = await driver.findComponent(ON.text('张三'));
      expect(card != null).assertTrue();
      if (card === null) {
        done();
        return;
      }
      const bounds = await card.getBounds();
      const cx = Math.floor((bounds.left + bounds.right) / 2);
      const cy = Math.floor((bounds.top + bounds.bottom) / 2);
      await driver.click(cx, cy);
      const bioVisible = await waitForText('知名女优简介', 6000);
      expect('detail bio=' + bioVisible).assertEqual('detail bio=true');
      const galleryEmpty = await waitForText('暂无写真', 3000);
      expect('gallery empty=' + galleryEmpty).assertEqual('gallery empty=true');
      const moviesVisible = await waitForText('关联影片', 3000);
      expect('movies=' + moviesVisible).assertEqual('movies=true');
      // 收藏流程（detail 在途防重/成功同步/失败保留）由 Actors JsUnit 覆盖；
      // '☆' 文本与列表卡片歧义，UiTest 不做收藏点击
      done();
    });
  });
}
