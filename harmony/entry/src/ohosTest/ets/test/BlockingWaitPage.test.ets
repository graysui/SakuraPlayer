/**
 * TASK-309 60 秒全屏等待 UiTest（真实运行时）。
 * 安全门禁：真实服务器配置或真实会话时跳过；干净设备注入 Fake 传输驱动认证态。
 * 用例链（同一 App 进程状态持续）：
 *   1) 进入等待页 + 系统 back 被锁定（全屏锁）
 *   2) 取消按钮 → 二次确认对话框 → 返回等待
 *   3) 再次取消 → 确认取消 → 退出等待页（回详情）
 *   4) 重新播放（Fake deadline 2s）→ 60 秒超时 → 提示切换来源且不取消任务
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { Driver, ON } from '@ohos.UiTest';
import { HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { authStore } from '../../../main/ets/core/auth/AuthStore';
import { ServerProfileStore } from '../../../main/ets/core/api/ServerProfile';
import { catalogImageCache } from '../../../main/ets/core/images/CatalogImageCache';

class QueuedResponse {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    this.status = status;
    this.body = body;
  }
}

class FakeHttpTransport implements HttpTransport {
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
      '"source_count":2,"progress":null}],"next_cursor":null}';
  }

  static movieDetailBody(): string {
    return '{"id":"m1","number":"ABC-001","title":"媒体库示例","title_original":null,' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,' +
      '"source_count":2,"progress":null,"metadata_state":"core_ready","metadata_error_code":null,' +
      '"release_date":"2026-01-02","maker":null,"series":null,"director":null,' +
      '"score":null,"description":null,"description_original":null,' +
      '"actors":[],"tags":[],"plot_image_urls":[],' +
      '"sources":[{"id":"10000000-0000-0000-0000-000000000001","website":"sehuatang",' +
      '"external_post_id":1,"title":"色花堂来源","publish_date":"2026-01-01","category":"中文字幕",' +
      '"labels":["subtitle"],"resource_size_mb":2048,"video_file_size_bytes":null,"availability":"ready"}]}';
  }

  static playResultStarted(deadlineIso: string): string {
    return '{"disposition":"started","wait_deadline":"' + deadlineIso + '",' +
      '"cache_job":{"id":"10000000-0000-0000-0000-0000000000c1","movie_id":"m1",' +
      '"source_id":"10000000-0000-0000-0000-000000000001","status":"submitting",' +
      '"remote_percent":null,"error_code":null,"media_candidates":[],"selected_media_ids":[],' +
      '"subtitles":[],"ready_at":null,"expires_at":null,' +
      '"created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}}';
  }

  static cancelBody(): string {
    return '{"id":"10000000-0000-0000-0000-0000000000c1","movie_id":"m1",' +
      '"source_id":"10000000-0000-0000-0000-000000000001","status":"cancelling",' +
      '"remote_percent":null,"error_code":null,"media_candidates":[],"selected_media_ids":[],' +
      '"subtitles":[],"ready_at":null,"expires_at":null,' +
      '"created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}';
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function deadlineInSeconds(seconds: number): string {
  return new Date(Date.now() + seconds * 1000).toISOString();
}

let uiDriver: Driver | null = null;
let fake: FakeHttpTransport | null = null;

async function waitForText(text: string, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (uiDriver === null) {
      return false;
    }
    const found = await uiDriver.findComponent(ON.text(text));
    if (found !== null) {
      return true;
    }
    await sleep(250);
  }
  return false;
}

async function clickText(text: string, timeoutMs: number): Promise<boolean> {
  if (uiDriver === null) {
    return false;
  }
  const found = await waitForText(text, timeoutMs);
  if (!found) {
    return false;
  }
  const component = await uiDriver.findComponent(ON.text(text));
  if (component === null) {
    return false;
  }
  const bounds = await component.getBounds();
  await uiDriver.click(Math.floor((bounds.left + bounds.right) / 2),
    Math.floor((bounds.top + bounds.bottom) / 2));
  return true;
}

export default function blockingWaitPageTest() {
  describe('BlockingWaitPageTest', () => {
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
      catalogImageCache.clear();
      uiDriver = Driver.create();
      fake = new FakeHttpTransport();
      fake.routes.set('/auth/bootstrap', new QueuedResponse(200, FakeHttpTransport.bootstrapBody(true)));
      fake.routes.set('/auth/login', new QueuedResponse(200, FakeHttpTransport.tokenBody()));
      fake.routes.set('/events/snapshot', new QueuedResponse(200, FakeHttpTransport.snapshotBody()));
      // 先插入更具体的路由（includes 先匹配者优先）
      fake.routes.set('/movies/m1/play-requests',
        new QueuedResponse(202, FakeHttpTransport.playResultStarted(deadlineInSeconds(30))));
      fake.routes.set('/cache-jobs/10000000-0000-0000-0000-0000000000c1/cancel',
        new QueuedResponse(202, FakeHttpTransport.cancelBody()));
      fake.routes.set('/movies/m1', new QueuedResponse(200, FakeHttpTransport.movieDetailBody()));
      fake.routes.set('/movies', new QueuedResponse(200, FakeHttpTransport.moviesBody()));
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
      uiDriver = null;
      fake = null;
      done();
    });

    it('enter_detail', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const libraryReady = await waitForText('媒体库示例', 4000);
      expect('library=' + libraryReady).assertEqual('library=true');
      await clickText('媒体库示例', 2500);
      const detailReady = await waitForText('点击选择来源', 4000);
      expect('detail=' + detailReady).assertEqual('detail=true');
      done();
    });

    it('select_source_enables_play', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      await clickText('点击选择来源', 2500);
      await sleep(500);
      const sourceReady = await waitForText('色花堂来源', 3000);
      expect('source=' + sourceReady).assertEqual('source=true');
      await clickText('色花堂来源', 2500);
      await sleep(600);
      // 选中后详情来源行显示选中来源（TASK-307 同款断言）
      const selected = await waitForText('色花堂 · 中文字幕 · 可播放', 3000);
      expect('selected=' + selected).assertEqual('selected=true');
      const playReady = await waitForText('播放', 3000);
      expect('play=' + playReady).assertEqual('play=true');
      done();
    });

    it('play_enters_waiting_and_locks_back', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      await clickText('播放', 2500);
      const waiting = await waitForText('正在准备播放', 4000);
      expect('waiting=' + waiting).assertEqual('waiting=true');
      // 系统 back 被锁定（全屏锁）
      if (uiDriver === null) {
        done();
        return;
      }
      await uiDriver.pressBack();
      await sleep(500);
      const stillWaiting = await waitForText('正在准备播放', 2000);
      expect('back locked=' + stillWaiting).assertEqual('back locked=true');
      done();
    });

    it('cancel_dialog_returns_to_waiting', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 从等待页：取消 → 对话框 → 返回等待
      const cancelClicked = await clickText('取消等待', 3000);
      expect('cancel clicked=' + cancelClicked).assertEqual('cancel clicked=true');
      const dialog = await waitForText('取消缓存任务？', 3000);
      expect('dialog=' + dialog).assertEqual('dialog=true');
      await clickText('返回等待', 3000);
      await sleep(500);
      const stillWaiting = await waitForText('正在准备播放', 2000);
      expect('still waiting=' + stillWaiting).assertEqual('still waiting=true');
      done();
    });

    it('confirmed_cancel_exits_waiting', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 从等待页：取消 → 确认取消 → 等待页自动退出（回详情，后续用例验证）
      const cancelClicked = await clickText('取消等待', 2500);
      expect('cancel clicked=' + cancelClicked).assertEqual('cancel clicked=true');
      const dialog = await waitForText('取消缓存任务？', 2500);
      expect('dialog=' + dialog).assertEqual('dialog=true');
      await clickText('确认取消', 2500);
      await sleep(600);
      const waitingGone = await waitForText('正在准备播放', 1200);
      expect('waiting gone=' + (waitingGone === false)).assertEqual('waiting gone=true');
      done();
    });

    it('timeout_replays_with_short_deadline', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 覆盖 play-requests 为 2 秒 deadline 后重新播放（详情仍在）
      if (fake === null) {
        done();
        return;
      }
      fake.routes.set('/movies/m1/play-requests',
        new QueuedResponse(202, FakeHttpTransport.playResultStarted(deadlineInSeconds(2))));
      const playReady = await waitForText('播放', 2500);
      expect('play=' + playReady).assertEqual('play=true');
      await clickText('播放', 2500);
      const waiting = await waitForText('正在准备播放', 3000);
      expect('waiting=' + waiting).assertEqual('waiting=true');
      done();
    });

    it('timeout_shows_exit_hint', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 2 秒 deadline 已过：超时视图提示切换来源（不取消任务）
      await sleep(2400);
      const timedOut = await waitForText('等待已结束，请切换来源', 2500);
      expect('timed out=' + timedOut).assertEqual('timed out=true');
      done();
    });

    it('timeout_returns_to_detail', 90000, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      await clickText('返回', 2500);
      await sleep(500);
      // 详情仍在（来源仍选中，播放按钮可见）
      const detailVisible = await waitForText('播放', 2000);
      expect('detail=' + detailVisible).assertEqual('detail=true');
      done();
    });
  });
}
