/**
 * TASK-305 排行榜页面 UiTest（真实运行时）。
 * 安全门禁：设备已有真实服务器配置或真实会话时跳过（保护真实数据）；
 * 干净设备：注入 Fake 传输驱动到认证态，点击排行榜 Tab 验证榜单 UI。
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { Driver, MatchPattern, ON } from '@ohos.UiTest';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { authStore } from '../../../main/ets/core/auth/AuthStore';
import { rankingsStore } from '../../../main/ets/features/rankings/RankingsStore';
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
      '"cache_queued":0,"cache_running":0,"cache_ready":0},' +
      '"cache_jobs":[],"metadata_jobs":[],' +
      '"cloud115_binding":{"bound":false,"status":"unbound","display_name":null,"cache_root_ready":false,"last_verified_at":null},"notifications":[]}';
  }

  static moviesBody(): string {
    return '{"items":[{"id":"m1","number":"ABC-001","title":"媒体库示例","title_original":null,' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,' +
      '"source_count":1,"progress":null}],"next_cursor":null}';
  }

  static rankingItemBody(rank: number, id: string, title: string): string {
    return `{"rank":${rank},"movie":{"id":"${id}","number":"R-${rank}","title":"${title}",` +
      `"title_original":null,"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],` +
      `"favorite":false,"source_count":1,"progress":null}}`;
  }

  static rankingBody(board: string, year: number | null, availableYears: number[],
    items: string, nextCursor: string | null): string {
    const yearsJson = availableYears.length === 0 ? '[]' : `[${availableYears.join(',')}]`;
    return `{"board":"${board}","year":${year === null ? 'null' : year},` +
      `"available_years":${yearsJson},"synced_at":"2026-08-04T12:00:00Z",` +
      `"items":${items},"next_cursor":${nextCursor === null ? 'null' : `"${nextCursor}"`}}`;
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

async function waitForTextContains(text: string, timeoutMs: number): Promise<boolean> {
  const driver = Driver.create();
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const found = await driver.findComponent(ON.text(text, MatchPattern.CONTAINS));
    if (found !== null) {
      return true;
    }
    await sleep(300);
  }
  return false;
}

export default function rankingsPageTest() {
  describe('RankingsPageTest', () => {
    let uiTestSkipped: boolean = false;

    beforeAll(async (done: Function) => {
      const appContext = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      // 安全门禁：真实服务器配置或真实会话时跳过，避免测试注入破坏真实数据
      const savedBase = await ServerProfileStore.load(appContext);
      const hasRealSession = await authStore.hasStoredRefreshToken();
      if (savedBase !== null || hasRealSession) {
        uiTestSkipped = true;
        hilog.warn(0x0000, 'T305UITEST', 'skipped: real server config or real session present');
        done();
        return;
      }
      // 隔离跨套件状态：重置排行榜单例（前序套件 logout 后残留 IDLE 也无妨，显式复位更稳）
      rankingsStore.detach();
      // 干净设备：注入 Fake 传输，驱动到认证态（媒体库/排行榜可用）
      const fake = new FakeHttpTransport();
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.bootstrapBody(true)));
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.tokenBody()));
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody()));
      // 媒体库 Tab 自动加载
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.moviesBody()));
      // 排行榜 Tab 首次激活 → 日榜
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.rankingBody('daily', null, [],
        `[${FakeHttpTransport.rankingItemBody(1, 'd1', '日榜影片')}]`, null)));
      // 切换到月榜
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.rankingBody('monthly', null, [],
        `[${FakeHttpTransport.rankingItemBody(2, 'm1', '月榜影片')}]`, null)));
      // 切换到 TOP250 总榜
      fake.responses.push(new QueuedResponse(200, FakeHttpTransport.rankingBody('top250', null, [2026, 2025],
        `[${FakeHttpTransport.rankingItemBody(3, 't1', '年度总榜影片')}]`, null)));
      authStore.setTransportForTesting(fake);
      await authStore.initialize(appContext);
      await authStore.configureServer('http://127.0.0.1:8000');
      await authStore.submitLogin('admin', 'pw');
            // TASK-313: entry UI 已渲染 UiTest 才能找到媒体库（登录后拉起，共享 authStore）
      await AbilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName: 'com.sakuraplayer.app',
        abilityName: 'EntryAbility',
      });
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

    it('rankings_tab_renders_daily_board_with_rank', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      // 先确认媒体库 Tab 已渲染（movies 响应已被消费），保证后续队列顺序稳定
      const libraryReady = await waitForText('媒体库示例', 6000);
      expect('library ready=' + libraryReady).assertEqual('library ready=true');
      // 点击底部"排行榜" Tab（坐标点击避免组件 click 偶发未命中）
      const tab = await driver.findComponent(ON.text('排行榜'));
      expect(tab != null).assertTrue();
      if (tab === null) {
        done();
        return;
      }
      const bounds = await tab.getBounds();
      const cx = Math.floor((bounds.left + bounds.right) / 2);
      // 屏幕底部为系统手势条区域，点击 tab 文字中心会被拦截；
      // 改点 tab 栏上部（图标区）以命中 TabContent 切换
      const cy = Math.max(0, bounds.top - 100);
      await driver.click(cx, cy);
      // 四榜单选择栏 + 日榜数据
      const boardVisible = await waitForText('日榜', 6000);
      expect('daily board=' + boardVisible).assertEqual('daily board=true');
      const weeklyVisible = await waitForText('周榜', 2000);
      expect('weekly tab=' + weeklyVisible).assertEqual('weekly tab=true');
      const movieVisible = await waitForText('日榜影片', 4000);
      expect('daily movie=' + movieVisible).assertEqual('daily movie=true');
      const rankVisible = await waitForText('1', 2000);
      expect('rank=' + rankVisible).assertEqual('rank=true');
      const syncedVisible = await waitForTextContains('更新于', 2000);
      expect('synced=' + syncedVisible).assertEqual('synced=true');
      done();
    });

    it('rankings_board_switch_to_monthly', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      const monthly = await driver.findComponent(ON.text('月榜'));
      expect(monthly != null).assertTrue();
      if (monthly === null) {
        done();
        return;
      }
      const bounds = await monthly.getBounds();
      const cx = Math.floor((bounds.left + bounds.right) / 2);
      const cy = Math.floor((bounds.top + bounds.bottom) / 2);
      await driver.click(cx, cy);
      const movieVisible = await waitForText('月榜影片', 5000);
      expect('monthly movie=' + movieVisible).assertEqual('monthly movie=true');
      done();
    });

    it('rankings_top250_shows_year_select', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      const top250 = await driver.findComponent(ON.text('TOP250'));
      expect(top250 != null).assertTrue();
      if (top250 === null) {
        done();
        return;
      }
      const bounds = await top250.getBounds();
      const cx = Math.floor((bounds.left + bounds.right) / 2);
      const cy = Math.floor((bounds.top + bounds.bottom) / 2);
      await driver.click(cx, cy);
      // TOP250 总榜：年份 Select（"总榜" value）只在 top250 出现
      const overallVisible = await waitForText('总榜', 5000);
      expect('top250 overall=' + overallVisible).assertEqual('top250 overall=true');
      const movieVisible = await waitForText('年度总榜影片', 4000);
      expect('top250 movie=' + movieVisible).assertEqual('top250 movie=true');
      done();
    });
  });
}
