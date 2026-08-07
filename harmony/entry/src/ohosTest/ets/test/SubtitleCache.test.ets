/**
 * TASK-311 SubtitleCache 测试：路径穿越/四格式/同名优先/生命周期（logout/cleaned/过期）。
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { fileIo as fs } from '@kit.CoreFileKit';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { SubtitleOption, TokenPair } from '../../../main/ets/core/api/ApiModels';
import { SubtitleCache } from '../../../main/ets/core/storage/SubtitleCache';

const SUBTITLE_ID = '50000000-0000-0000-0000-0000000000a1';
const JOB_ID = '10000000-0000-0000-0000-0000000000c1';

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

class FakeHttpTransport implements HttpTransport {
  routes: Map<string, HttpResponse> = new Map();
  subtitleRequests: number = 0;

  request(request: HttpRequest): Promise<HttpResponse> {
    if (request.url.includes('/playback/subtitles/')) {
      if (request.url.includes('c9')) {
        const missing: HttpResponse = { statusCode: 404, body: '{"code":"subtitle_not_found","message":"x","request_id":"r1"}' };
        return Promise.resolve(missing);
      }
      this.subtitleRequests++;
      const ok: HttpResponse = { statusCode: 200, body: '1\n00:00:01,000 --> 00:00:03,000\n你好' };
      return Promise.resolve(ok);
    }
    return Promise.reject(new Error(`no route for ${request.url}`));
  }
}

function subtitle(format: string, id: string): SubtitleOption {
  return new SubtitleOption(id, null, '测试字幕', format, 'zh', false);
}

export default function subtitleCacheTest() {
  describe('SubtitleCache', () => {
    let cacheDir: string;
    let client: ApiClient;
    let transport: FakeHttpTransport;

    beforeAll(async (done: Function) => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      cacheDir = SubtitleCache.dir(context);
      // 清理残留
      await SubtitleCache.clear(context);
      transport = new FakeHttpTransport();
      client = new ApiClient(transport, 'http://test/api/v1', new FakeSession());
      done();
    });

    afterAll(async (done: Function) => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      await SubtitleCache.clear(context);
      done();
    });

    it('path_for_rejects_non_uuid_and_unknown_format', 0, () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      // 非法 id
      expect(SubtitleCache.isSafeId('../../evil', 'srt')).assertFalse();
      expect(SubtitleCache.isSafeId('not-a-uuid', 'srt')).assertFalse();
      // 非法格式
      expect(SubtitleCache.isSafeId(SUBTITLE_ID, 'exe')).assertFalse();
      expect(SubtitleCache.isSafeId(SUBTITLE_ID, 'mp4')).assertFalse();
      // 合法
      expect(SubtitleCache.isSafeId(SUBTITLE_ID, 'srt')).assertTrue();
      expect(SubtitleCache.isSafeId(SUBTITLE_ID, 'ass')).assertTrue();
      expect(SubtitleCache.isSafeId(SUBTITLE_ID, 'ssa')).assertTrue();
      expect(SubtitleCache.isSafeId(SUBTITLE_ID, 'vtt')).assertTrue();
    });

    it('downloads_four_formats_and_writes_files', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      const formats: string[] = ['srt', 'ass', 'ssa', 'vtt'];
      for (let i = 0; i < formats.length; i++) {
        const id = `50000000-0000-0000-0000-0000000000b${i}`;
        const sub = subtitle(formats[i], id);
        const path = await SubtitleCache.download(context, client, sub, JOB_ID);
        expect(path !== null).assertTrue();
        if (path !== null) {
          const text = fs.readTextSync(path);
          expect(text.includes('你好')).assertTrue();
        }
      }
    });

    it('same_id_reuses_existing_copy', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      const sub = subtitle('srt', SUBTITLE_ID);
      const path1 = await SubtitleCache.download(context, client, sub, JOB_ID);
      expect(path1 !== null).assertTrue();
      const requestsAfterFirst = transport.subtitleRequests;
      const path2 = await SubtitleCache.download(context, client, sub, JOB_ID);
      expect(path2).assertEqual(path1);
      // 二次 download 不重复请求（同名优先）
      expect(transport.subtitleRequests).assertEqual(requestsAfterFirst);
    });

    it('download_failure_returns_null_without_blocking', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      const sub = subtitle('srt', '50000000-0000-0000-0000-0000000000c9');
      // 路由不存在 → 404 subtitle_not_found → null
      const path = await SubtitleCache.download(context, client, sub, JOB_ID);
      expect(path).assertNull();
    });

    it('remove_for_job_deletes_only_that_job_files', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      const otherJob = '20000000-0000-0000-0000-0000000000d1';
      const subA = subtitle('srt', '50000000-0000-0000-0000-0000000000e1');
      const subB = subtitle('vtt', '50000000-0000-0000-0000-0000000000e2');
      await SubtitleCache.download(context, client, subA, JOB_ID);
      await SubtitleCache.download(context, client, subB, otherJob);
      expect(SubtitleCache.exists(context, subA.id)).assertTrue();
      expect(SubtitleCache.exists(context, subB.id)).assertTrue();
      // 清理 JOB_ID → 只删 subA
      await SubtitleCache.removeForJob(context, JOB_ID);
      expect(SubtitleCache.exists(context, subA.id)).assertFalse();
      expect(SubtitleCache.exists(context, subB.id)).assertTrue();
    });

    it('clear_removes_all_subtitles_but_other_dirs_untouched', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      // 在 cacheDir 放一个"永久图片"目录（模拟 gfriends）
      const imageDir = `${context.cacheDir}/gfriends-v1`;
      try {
        if (!fs.accessSync(imageDir)) {
          fs.mkdirSync(imageDir, true);
        }
        const fd = fs.openSync(`${imageDir}/keep.png`,
          fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
        fs.writeSync(fd.fd, 'png');
        fs.closeSync(fd.fd);
      } catch (err) {
        // 目录创建失败忽略
      }
      await SubtitleCache.clear(context);
      expect(fs.accessSync(SubtitleCache.dir(context))).assertFalse();
      // 永久图片目录不被删除
      expect(fs.accessSync(imageDir)).assertTrue();
    });

    it('remove_expired_clears_all', 0, async () => {
      const context = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
      const sub = subtitle('srt', SUBTITLE_ID);
      await SubtitleCache.download(context, client, sub, JOB_ID);
      expect(SubtitleCache.exists(context, sub.id)).assertTrue();
      await SubtitleCache.removeExpired(context);
      expect(SubtitleCache.exists(context, sub.id)).assertFalse();
    });
  });
}
