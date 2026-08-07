/**
 * TASK-307 影片详情/来源选择 UiTest（真实运行时）。
 * 安全门禁：真实服务器配置或真实会话时跳过；干净设备注入 Fake 传输驱动认证态。
 * fixture 不含真实图片 URL（cover_url/plot_image_urls 为空），无真实网络访问。
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
    return '{"id":"m1","number":"ABC-001","title":"媒体库示例","title_original":"Media Example",' +
      '"cover_url":null,"publish_date":"2026-01-01","labels":["subtitle"],"favorite":false,' +
      '"source_count":2,"progress":{"position_seconds":600,"duration_seconds":3600,' +
      '"completed":false,"version":1},"metadata_state":"core_ready","metadata_error_code":null,' +
      '"release_date":"2026-01-02","maker":"厂商A","series":"系列B","director":"导演C",' +
      '"score":8.5,"description":"这是中文简介","description_original":"en",' +
      '"actors":[{"id":"a1","display_name":"张三","name_ja":"张三","name_zh":null,' +
      '"aliases":["张三别名"],"profile_url":null,"favorite":false}],' +
      '"tags":["长发","剧情"],"plot_image_urls":[],' +
      '"sources":[{"id":"10000000-0000-0000-0000-000000000001","website":"sehuatang","external_post_id":1,"title":"色花堂来源",' +
      '"publish_date":"2026-01-01","category":"中文字幕","labels":["subtitle"],' +
      '"resource_size_mb":2048,"video_file_size_bytes":null,"availability":"ready"},' +
      '{"id":"10000000-0000-0000-0000-000000000002","website":"x1080x","external_post_id":2,"title":"X1080X来源",' +
      '"publish_date":null,"category":"亚洲无码","labels":["cracked","4k"],' +
      '"resource_size_mb":null,"video_file_size_bytes":3221225472,"availability":"rejected"}]}';
  }

  static movieDetailBodyWithoutTranslation(): string {
    return FakeHttpTransport.movieDetailBody().replace('"description":"这是中文简介"', '"description":null')
      .replace('"description_original":"en"', '"description_original":"原文简介"');
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

export default function movieDetailPageTest() {
  describe('MovieDetailPageTest', () => {
    let uiTestSkipped: boolean = false;
    let fake: FakeHttpTransport | null = null;

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
      fake = new FakeHttpTransport();
      fake.routes.set('/auth/bootstrap', new QueuedResponse(200, FakeHttpTransport.bootstrapBody(true)));
      fake.routes.set('/auth/login', new QueuedResponse(200, FakeHttpTransport.tokenBody()));
      fake.routes.set('/events/snapshot', new QueuedResponse(200, FakeHttpTransport.snapshotBody()));
      // 先插入更具体的路由（includes 先匹配者优先）；详情/收藏必须先于列表
      fake.routes.set('/movies/m1/favorite', new QueuedResponse(204, ''));
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
      done();
    });

    it('movie_detail_renders_all_sections', 30, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      const libraryReady = await waitForText('媒体库示例', 6000);
      expect('library ready=' + libraryReady).assertEqual('library ready=true');
      // 点击媒体库卡片进入详情
      const card = await driver.findComponent(ON.text('媒体库示例'));
      expect(card != null).assertTrue();
      if (card === null) {
        done();
        return;
      }
      const bounds = await card.getBounds();
      await driver.click(Math.floor((bounds.left + bounds.right) / 2),
        Math.floor((bounds.top + bounds.bottom) / 2));
      // 详情字段
      const sourceSection = await waitForText('来源（2）', 6000);
      expect('sources=' + sourceSection).assertEqual('sources=true');
      const description = await waitForText('这是中文简介', 3000);
      expect('description=' + description).assertEqual('description=true');
      const plotEmpty = await waitForText('暂无剧照', 3000);
      expect('plot empty=' + plotEmpty).assertEqual('plot empty=true');
      const actor = await waitForText('张三', 3000);
      expect('actor=' + actor).assertEqual('actor=true');
      const progress = await waitForText('继续播放 17%', 3000);
      expect('progress=' + progress).assertEqual('progress=true');
      const date = await waitForText('日期：2026-01-02', 3000);
      expect('date=' + date).assertEqual('date=true');
      done();
    });

    it('movie_detail_falls_back_to_original_description', 30, async (done: Function) => {
      if (uiTestSkipped || fake === null) {
        done();
        return;
      }
      const driver = Driver.create();
      // 从详情页返回列表，再以“译文缺失”的详情响应进入
      await driver.pressBack();
      await sleep(800);
      fake.routes.set('/movies/m1',
        new QueuedResponse(200, FakeHttpTransport.movieDetailBodyWithoutTranslation()));
      const card = await driver.findComponent(ON.text('媒体库示例'));
      expect(card != null).assertTrue();
      if (card === null) {
        done();
        return;
      }
      const bounds = await card.getBounds();
      await driver.click(Math.floor((bounds.left + bounds.right) / 2),
        Math.floor((bounds.top + bounds.bottom) / 2));
      const fallback = await waitForText('原文简介（原文）', 6000);
      expect('fallback=' + fallback).assertEqual('fallback=true');
      const emptyPlaceholder = await waitForText('暂无中文简介', 1500);
      expect('no old placeholder=' + emptyPlaceholder).assertEqual('no old placeholder=false');
      fake.routes.set('/movies/m1', new QueuedResponse(200, FakeHttpTransport.movieDetailBody()));
      done();
    });

    it('source_sheet_shows_rows_and_selects_source', 30, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      const sourceRow = await waitForText('点击选择来源', 6000);
      expect('source row=' + sourceRow).assertEqual('source row=true');
      // 打开来源 sheet
      const row = await driver.findComponent(ON.text('点击选择来源'));
      expect(row != null).assertTrue();
      if (row === null) {
        done();
        return;
      }
      const rowBounds = await row.getBounds();
      await driver.click(Math.floor((rowBounds.left + rowBounds.right) / 2),
        Math.floor((rowBounds.top + rowBounds.bottom) / 2));
      const sheetTitle = await waitForText('选择来源（2）', 5000);
      expect('sheet title=' + sheetTitle).assertEqual('sheet title=true');
      const readySource = await waitForText('色花堂来源', 3000);
      expect('ready source=' + readySource).assertEqual('ready source=true');
      const availability = await waitForText('可播放', 3000);
      expect('availability=' + availability).assertEqual('availability=true');
      const size = await waitForText('视频文件大小未知', 3000);
      expect('size=' + size).assertEqual('size=true');
      // 选择来源（点击行标题）
      const sourceTitle = await driver.findComponent(ON.text('色花堂来源'));
      expect(sourceTitle != null).assertTrue();
      if (sourceTitle === null) {
        done();
        return;
      }
      const sourceBounds = await sourceTitle.getBounds();
      await driver.click(Math.floor((sourceBounds.left + sourceBounds.right) / 2),
        Math.floor((sourceBounds.top + sourceBounds.bottom) / 2));
      // sheet 关闭，详情来源行显示选中来源
      const selected = await waitForText('色花堂 · 中文字幕 · 可播放', 5000);
      expect('selected=' + selected).assertEqual('selected=true');
      done();
    });

    it('favorite_button_toggles', 30, async (done: Function) => {
      if (uiTestSkipped) {
        done();
        return;
      }
      const driver = Driver.create();
      const favoriteButton = await waitForText('☆ 收藏', 6000);
      expect('favorite button=' + favoriteButton).assertEqual('favorite button=true');
      const button = await driver.findComponent(ON.text('☆ 收藏'));
      expect(button != null).assertTrue();
      if (button === null) {
        done();
        return;
      }
      const bounds = await button.getBounds();
      await driver.click(Math.floor((bounds.left + bounds.right) / 2),
        Math.floor((bounds.top + bounds.bottom) / 2));
      const favorited = await waitForText('★ 已收藏', 5000);
      expect('favorited=' + favorited).assertEqual('favorited=true');
      done();
    });
  });
}
