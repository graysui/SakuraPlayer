/**
 * TASK-313 HarmonyOS 端到端用户旅程（Fake 后端）。
 * 链式用例（同一 App 进程状态持续）：
 *   1) 登录后媒体库 → 三 Tab 导航（媒体库/排行榜/女优）→ 全局搜索
 *   2) 六分类筛选 → 榜单切换 → 女优详情 → 影片详情多来源 → 播放等待 → 取消
 *   3) 设置页（115/连接测试）→ 诊断页（组件状态/失败记录）
 * 安全门禁：真实服务器配置或真实会话时跳过；默认套件零真实外部访问（AC-128）。
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { Driver, ON } from '@ohos.UiTest';
import { HttpRequest, HttpResponse, HttpTransport } from '../../../main/ets/core/api/ApiClient';
import { authStore } from '../../../main/ets/core/auth/AuthStore';
import { ServerProfileStore } from '../../../main/ets/core/api/ServerProfile';
import { catalogImageCache } from '../../../main/ets/core/images/CatalogImageCache';

class RouteResponse {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    this.status = status;
    this.body = body;
  }
}

class FakeHttpTransport implements HttpTransport {
  routes: Map<string, RouteResponse> = new Map();

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
      '"cloud115_binding":{"bound":false,"status":"unknown","display_name":null,"cache_root_ready":false,"last_verified_at":null},"notifications":[]}';
  }

  static movieItem(id: string, number: string, title: string): string {
    return `{"id":"${id}","number":"${number}","title":"${title}","title_original":null,` +
      `"cover_url":null,"publish_date":"2026-01-01","labels":[],"favorite":false,` +
      `"source_count":1,"progress":null}`;
  }

  static moviesBody(): string {
    return `{"items":[${FakeHttpTransport.movieItem('j1', 'JRN-001', '旅程影片一')},` +
      `${FakeHttpTransport.movieItem('j2', 'JRN-002', '旅程影片二')}],"next_cursor":null}`;
  }

  static movieDetailBody(): string {
    return '{"id":"j1","number":"JRN-001","title":"旅程影片一","title_original":null,' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":[],"favorite":false,' +
      '"source_count":1,"progress":null,"metadata_state":"core_ready","metadata_error_code":null,' +
      '"release_date":"2026-01-02","maker":null,"series":null,"director":null,' +
      '"score":null,"description":"旅程影片简介","description_original":null,' +
      '"actors":[],"tags":[],"plot_image_urls":[],' +
      '"sources":[{"id":"10000000-0000-0000-0000-000000000001","website":"sehuatang",' +
      '"external_post_id":1,"title":"旅程来源","publish_date":"2026-01-01","category":"中文字幕",' +
      '"labels":["subtitle"],"resource_size_mb":2048,"video_file_size_bytes":null,"availability":"ready"}]}';
  }

  static playResultStarted(): string {
    return '{"disposition":"started","wait_deadline":"' +
      new Date(Date.now() + 30 * 1000).toISOString() + '",' +
      '"cache_job":{"id":"10000000-0000-0000-0000-0000000000c1","movie_id":"j1",' +
      '"source_id":"10000000-0000-0000-0000-000000000001","status":"submitting",' +
      '"remote_percent":null,"error_code":null,"media_candidates":[],"selected_media_ids":[],' +
      '"subtitles":[],"ready_at":null,"expires_at":null,' +
      '"created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}}';
  }

  static cancelBody(): string {
    return '{"id":"10000000-0000-0000-0000-0000000000c1","movie_id":"j1",' +
      '"source_id":"10000000-0000-0000-0000-000000000001","status":"cancelling",' +
      '"remote_percent":null,"error_code":null,"media_candidates":[],"selected_media_ids":[],' +
      '"subtitles":[],"ready_at":null,"expires_at":null,' +
      '"created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}';
  }

  static rankingBody(board: string): string {
    return `{"board":"${board}","year":null,"available_years":[],` +
      `"synced_at":"2026-08-06T00:00:00Z","items":[{"rank":1,"movie":` +
      `${FakeHttpTransport.movieItem('j1', 'JRN-001', '旅程影片一')}}],"next_cursor":null}`;
  }

  static actorsBody(): string {
    return '{"items":[' +
      '{"id":"a1","display_name":"旅程女优一","name_ja":"旅程女优一","name_zh":null,' +
      '"aliases":[],"profile_url":null,"favorite":false},' +
      '{"id":"a2","display_name":"旅程女优二","name_ja":"旅程女优二","name_zh":null,' +
      '"aliases":[],"profile_url":null,"favorite":false}],"next_cursor":null}';
  }

  static actorDetailBody(): string {
    return '{"id":"a1","display_name":"旅程女优一","name_ja":"旅程女优一","name_zh":null,' +
      '"aliases":[],"profile_url":null,"favorite":false,' +
      '"bio":"旅程女优简介","bio_original":null,"gallery_urls":[],' +
      '"movies":[{"id":"j1","number":"JRN-001","title":"旅程影片一","title_original":null,' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":[],"favorite":false,' +
      '"source_count":1,"progress":null}]}';
  }

  static searchBody(): string {
    return '{"movies":[' +
      '{"id":"j3","number":"SRC-001","title":"搜索结果影片","title_original":null,' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":[],"favorite":false,' +
      '"source_count":1,"progress":null}],' +
      '"actors":[{"id":"a1","display_name":"旅程女优一","name_ja":"旅程女优一","name_zh":null,' +
      '"aliases":[],"profile_url":null,"favorite":false}],' +
      '"pending_metadata":[]}';
  }

  static settingsBody(): string {
    return '{"cache_ttl_hours":24,"ready_cache_limit":20,"metadata_concurrency":3,' +
      '"metadata_timeout_seconds":600,' +
      '"javdb":{"configured":false,"status":"unknown","last_checked_at":null,' +
      '"last_error_code":null,"username":null,"password_configured":false,"version":1},' +
      '"ai":{"configured":false,"status":"unknown","last_checked_at":null,' +
      '"last_error_code":null,"base_url":null,"model":null,"timeout_seconds":60,' +
      '"api_key_configured":false,"version":1},' +
      '"mgdb":{"configured":false,"source_url":null,"version":1},' +
      '"providers":{"cloud115":{"configured":false,"status":"unknown","last_checked_at":null,' +
      '"last_error_code":null},"dmm":{"configured":false,"status":"unknown",' +
      '"last_checked_at":null,"last_error_code":null}},';
  }

  static settingsBodyTail(): string {
    return '"avdb_sync":{"incremental_30d":{"status":"never","imported_count":0,"release_id":null,' +
      '"last_successful_at":null,"next_scheduled_at":null},"full_reconcile":{"status":"never",' +
      '"imported_count":0,"release_id":null,"last_successful_at":null,"next_scheduled_at":null}}}';
  }

  static diagnosticsBody(): string {
    return '{"generated_at":"2026-08-06T00:00:00Z",' +
      '"components":[{"component":"api","status":"healthy","error_code":null,' +
      '"checked_at":"2026-08-06T00:00:00Z"}],' +
      '"queues":{"metadata_queued":0,"metadata_running":0,"metadata_paused":false,' +
      '"cache_queued":0,"cache_running":0,"cache_ready":0},' +
      '"metadata_progress":{"total":42,"queued":0,"running":0,"completed":42,"failed":0,' +
      '"finished":42,"current_numbers":[]},' +
      '"recent_failures":[],' +
      '"connection_tests":[{"target":"cloud115","status":"not_configured","error_code":null,' +
      '"elapsed_ms":0,"checked_at":"2026-08-06T00:00:00Z"}]}';
  }

  static connectionTestBody(): string {
    return '{"target":"metadata","status":"ok","error_code":null,"elapsed_ms":12,' +
      '"checked_at":"2026-08-06T00:00:00Z"}';
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
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

async function clickTab(text: string, timeoutMs: number): Promise<boolean> {
  // 底部 Tab：先尝试组件 click；若 400ms 后仍停在原页，退回 tab 栏上部坐标
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
  // TASK-306 同款：点 tab 文本上方 100px（避开系统手势条；ActorsPage.test 实测有效）
  const cx = Math.floor((bounds.left + bounds.right) / 2);
  const cy = Math.max(0, bounds.top - 100);
  await uiDriver.click(cx, cy);
  return true;
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

export default function harmonyUserJourneyTest() {
  describe('HarmonyUserJourneyTest', () => {
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
      // 先插入更具体的路由（includes 先匹配者优先）
      fake.routes.set('/auth/bootstrap', new RouteResponse(200, FakeHttpTransport.bootstrapBody(true)));
      fake.routes.set('/auth/login', new RouteResponse(200, FakeHttpTransport.tokenBody()));
      fake.routes.set('/events/snapshot', new RouteResponse(200, FakeHttpTransport.snapshotBody()));
      fake.routes.set('/movies/j1/play-requests',
        new RouteResponse(202, FakeHttpTransport.playResultStarted()));
      fake.routes.set('/cache-jobs/10000000-0000-0000-0000-0000000000c1/cancel',
        new RouteResponse(202, FakeHttpTransport.cancelBody()));
      fake.routes.set('/movies/j1', new RouteResponse(200, FakeHttpTransport.movieDetailBody()));
      fake.routes.set('/movies', new RouteResponse(200, FakeHttpTransport.moviesBody()));
      fake.routes.set('board=daily', new RouteResponse(200, FakeHttpTransport.rankingBody('daily')));
      fake.routes.set('board=weekly', new RouteResponse(200, FakeHttpTransport.rankingBody('weekly')));
      fake.routes.set('/actors/a1', new RouteResponse(200, FakeHttpTransport.actorDetailBody()));
      fake.routes.set('/actors', new RouteResponse(200, FakeHttpTransport.actorsBody()));
      fake.routes.set('/search', new RouteResponse(200, FakeHttpTransport.searchBody()));
      fake.routes.set('/settings/connection-tests',
        new RouteResponse(200, FakeHttpTransport.connectionTestBody()));
      fake.routes.set('/settings', new RouteResponse(200,
        FakeHttpTransport.settingsBody() + FakeHttpTransport.settingsBodyTail()));
      fake.routes.set('/diagnostics', new RouteResponse(200, FakeHttpTransport.diagnosticsBody()));
      fake.routes.set('/admin/metadata-jobs',
        new RouteResponse(200, '{"items":[],"next_cursor":null}'));
      fake.routes.set('/cache-jobs', new RouteResponse(200,
        '{"items":[],"next_cursor":null}'));
      authStore.setTransportForTesting(fake);
      await authStore.initialize(appContext);
      await authStore.configureServer('http://127.0.0.1:8000');
      await authStore.submitLogin('admin', 'pw');
      await sleep(1500);
      // TASK-313：entry UI 未渲染时 UiTest 找不到媒体库（aa test 只启动 TestAbility）；
      // 登录后 startAbility 拉起 entry，共享 authStore 直接显示媒体库
      const visible = await waitForText('旅程影片一', 2000);
      if (!visible) {
        const delegator = AbilityDelegatorRegistry.getAbilityDelegator();
        await delegator.startAbility({
          bundleName: 'com.sakuraplayer.app',
          abilityName: 'EntryAbility',
        });
        await sleep(2500);
      }
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

    it('journey_library_and_three_tabs', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 登录完成 → 媒体库（AC-060 主入口）
      const libraryReady = await waitForText('旅程影片一', 3500);
      expect('library=' + libraryReady).assertEqual('library=true');
      // 三 Tab 导航（AC-059/060）：排行榜 → 女优 → 回媒体库
      const toRankings = await clickTab('排行榜', 2500);
      expect('tab-rankings=' + toRankings).assertEqual('tab-rankings=true');
      const rankingsReady = await waitForText('日榜', 4500);
      expect('rankings=' + rankingsReady).assertEqual('rankings=true');
      const toActors = await clickTab('女优', 2500);
      expect('tab-actors=' + toActors).assertEqual('tab-actors=true');
      const actorsReady = await waitForText('旅程女优一', 3000);
      expect('actors=' + actorsReady).assertEqual('actors=true');
      const backToLibrary = await clickTab('媒体库', 2500);
      expect('tab-library=' + backToLibrary).assertEqual('tab-library=true');
      const libraryAgain = await waitForText('旅程影片一', 3000);
      expect('library-again=' + libraryAgain).assertEqual('library-again=true');
      done();
    });

    it('journey_catalog_filter_and_rankings', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 六分类筛选（AC-063）：点「中文字幕」chip，列表仍可用
      const categoryClicked = await clickText('中文字幕', 2500);
      expect('category=' + categoryClicked).assertEqual('category=true');
      await sleep(300);
      const listStillThere = await waitForText('旅程影片一', 2500);
      expect('list-after-filter=' + listStillThere).assertEqual('list-after-filter=true');
      // 六分类（AC-063）再点一类（4K原版），列表仍可用
      const secondCategory = await clickText('4K原版', 2000);
      expect('category2=' + secondCategory).assertEqual('category2=true');
      await sleep(300);
      const listAfterSecond = await waitForText('旅程影片一', 2000);
      expect('list-after-filter2=' + listAfterSecond).assertEqual('list-after-filter2=true');
      // 榜单切换（AC-070）：日榜 → 周榜
      await clickTab('排行榜', 2500);
      const weeklyClicked = await clickText('周榜', 2500);
      expect('weekly=' + weeklyClicked).assertEqual('weekly=true');
      const weeklyShown = await waitForText('周榜', 3500);
      expect('weekly-shown=' + weeklyShown).assertEqual('weekly-shown=true');
      done();
    });

    it('journey_actor_detail', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 女优详情（AC-076）：写真
      await clickTab('女优', 2500);
      const actorClicked = await clickText('旅程女优一', 2500);
      expect('actor=' + actorClicked).assertEqual('actor=true');
      const detailReady = await waitForText('写真', 3000);
      expect('actor-detail=' + detailReady).assertEqual('actor-detail=true');
      done();
    });

    it('journey_movie_detail_sources', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 回媒体库（系统 back + Tab）
      if (uiDriver !== null) {
        await uiDriver.pressBack();
      }
      await sleep(400);
      await clickTab('媒体库', 2500);
      // 影片详情多来源（AC-074/084）
      const movieClicked = await clickText('旅程影片一', 3000);
      expect('movie=' + movieClicked).assertEqual('movie=true');
      const sourceReady = await waitForText('点击选择来源', 3000);
      expect('detail=' + sourceReady).assertEqual('detail=true');
      await clickText('点击选择来源', 2000);
      const sourceShown = await waitForText('旅程来源', 2500);
      expect('source=' + sourceShown).assertEqual('source=true');
      await clickText('旅程来源', 2000);
      await sleep(400);
      const playReady = await waitForText('播放', 2500);
      expect('play=' + playReady).assertEqual('play=true');
      done();
    });

    it('journey_play_wait_and_cancel', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 播放 → 全屏等待（AC-086/087）
      const playClicked = await clickText('播放', 2500);
      expect('play-clicked=' + playClicked).assertEqual('play-clicked=true');
      const waitingReady = await waitForText('正在准备播放', 3000);
      expect('waiting=' + waitingReady).assertEqual('waiting=true');
      // 取消（二次确认，AC-086 唯一出口）
      const cancelClicked = await clickText('取消等待', 2500);
      expect('cancel=' + cancelClicked).assertEqual('cancel=true');
      const dialogReady = await waitForText('取消缓存任务？', 2000);
      expect('dialog=' + dialogReady).assertEqual('dialog=true');
      await clickText('确认取消', 2000);
      await sleep(400);
      const waitingGone = await waitForText('正在准备播放', 2000);
      expect('waiting-gone=' + (waitingGone === false)).assertEqual('waiting-gone=true');
      done();
    });

    it('journey_settings_page', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 顶部设置入口（AC-061）→ 设置页（AC-119：115 绑定区）
      // 上一个用例停留在详情页：先返回 Tab 容器（详情页无顶部设置入口）
      if (uiDriver !== null) {
        await uiDriver.pressBack();
      }
      await sleep(400);
      const settingsClicked = await clickText('设置', 2500);
      expect('settings=' + settingsClicked).assertEqual('settings=true');
      const cloudReady = await waitForText('115 云盘', 3000);
      expect('cloud=' + cloudReady).assertEqual('cloud=true');
      const unboundReady = await waitForText('未绑定 115 账号', 2500);
      expect('unbound=' + unboundReady).assertEqual('unbound=true');
      done();
    });

    it('journey_diagnostics_page', 0, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      // 诊断入口（AC-121）：设置页底部按钮，相对化滚动后查找（不依赖固定分辨率）
      let diagClicked = false;
      if (uiDriver !== null) {
        const display = await uiDriver.getDisplaySize();
        const midX = Math.floor(display.x / 2);
        const startY = Math.floor(display.y * 0.7);
        const endY = Math.floor(display.y * 0.15);
        await uiDriver.swipe(midX, startY, midX, endY, 400);
        await sleep(400);
        diagClicked = await clickText('诊断信息', 3000);
        if (!diagClicked) {
          await uiDriver.swipe(midX, startY, midX, endY, 400);
          await sleep(400);
          diagClicked = await clickText('诊断信息', 3000);
        }
      }
      expect('diag=' + diagClicked).assertEqual('diag=true');
      const componentsReady = await waitForText('组件状态', 3000);
      expect('components=' + componentsReady).assertEqual('components=true');
      const queueReady = await waitForText('队列与进度', 2500);
      expect('queue=' + queueReady).assertEqual('queue=true');
      done();
    });

    it('journey_search_overlay', 0, async (done: Function) => {
      // 放最后：搜索面板（bindSheet）不关闭，避免遮挡后续用例
      if (uiTestSkipped) {
        done();
        return;
      }
      // 上一用例停在诊断页：循环返回直到 Tab 容器（NavDestination 无顶部搜索入口）
      if (uiDriver !== null) {
        for (let i = 0; i < 3; i++) {
          const topShown = await waitForText('搜索', 1000);
          if (topShown) {
            break;
          }
          await uiDriver.pressBack();
          await sleep(300);
        }
      }
      const searchClicked = await clickText('搜索', 2500);
      expect('search=' + searchClicked).assertEqual('search=true');
      const panelReady = await waitForText('全局搜索', 2500);
      expect('panel=' + panelReady).assertEqual('panel=true');
      // 查询与结果分组语义由 AppNavigation.test（SearchStoreTest）JsUnit 覆盖；
      // 此处验证搜索入口与面板可达（AC-061 顶部全局搜索）
      done();
    });
  });
}
