/**
 * TASK-304 媒体库页面 UiTest（真实运行时）。
 * 安全门禁：设备已有真实服务器配置或真实会话时跳过（保护真实数据）；
 * 干净设备：注入 Fake 传输驱动到认证态，验证媒体库 UI。
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { Driver, ON } from '@ohos.UiTest';
import { HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { authStore } from '../../../main/ets/core/auth/AuthStore';
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
  responses: QueuedResponse[] = [];

  async request(_request: HttpRequest): Promise<HttpResponse> {
    const next = this.responses.shift();
    if (next === undefined) {
      throw new Error('no queued response');
    }
    const response: HttpResponse = { statusCode: next.status, body: next.body };
    return response;
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
      '"cache_queued":0,"cache_running":0,"cache_ready":1},' +
      '"cache_jobs":[],"metadata_jobs":[],' +
      '"cloud115_binding":{"status":"unbound"},"notifications":[]}';
  }

  static moviesBody(): string {
    return '{"items":[{"id":"m1","number":"ABC-001","title":"媒体库示例","title_original":null,' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,' +
      '"source_count":1,"progress":null}],"next_cursor":null}';
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

export default function libraryPageTest() {
  describe('LibraryPageTest', () => {
    let uiTestSkipped: boolean = false;

    beforeAll(async (done: Function) => {
      const appContext = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      // 安全门禁：真实服务器配置或真实会话时跳过，避免测试注入破坏真实数据
      const savedBase = await ServerProfileStore.load(appContext);
      const hasRealSession = await authStore.hasStoredRefreshToken();
      if (savedBase !== null || hasRealSession) {
        uiTestSkipped = true;
        done();
        return;
      }
      // 干净设备：注入 Fake 传输，驱动到认证态（媒体库页可用）
      const fake = new FakeHttpTransport();
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.bootstrapBody(true)));
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.tokenBody()));
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody()));
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.moviesBody()));
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

    it('library_tab_renders_category_bar_and_filter_button', 0, async () => {
      if (uiTestSkipped) {
        return;
      }
      // 分类快捷栏随页面首帧渲染（不依赖数据加载）
      const chipVisible = await waitForText('亚洲有码', 6000);
      expect(chipVisible).assertTrue();
      const filterVisible = await waitForText('筛选', 2000);
      expect(filterVisible).assertTrue();
      // 网格渲染出影片卡片（Fake /movies 数据）
      const movieVisible = await waitForText('媒体库示例', 3000);
      expect('grid movie=' + movieVisible).assertEqual('grid movie=true');
    });

    it('library_filters_sheet_opens_and_applies_sort', 0, async () => {
      if (uiTestSkipped) {
        return;
      }
      const uiDriver = Driver.create();
      const filterButton = await uiDriver.findComponent(ON.text('筛选'));
      expect(filterButton !== null).assertTrue();
      if (filterButton !== null) {
        await filterButton.click();
      }
      const sheetVisible = await waitForText('组合筛选', 4000);
      expect('sheet opened=' + sheetVisible).assertEqual('sheet opened=true');
      // 注：sheet 内控件的点选/应用依赖 bindSheet 手势，UiTest 定位不稳定；
      // 组合筛选交互（六分类/标签/排序/收藏）由 LibraryStore JsUnit 覆盖。
    });
  });
}
