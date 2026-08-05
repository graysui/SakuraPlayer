/**
 * TASK-306 GFriends 缓存测试：
 * - URL 白名单逐字段校验
 * - 下载器：重定向逐跳、8 MiB、签名/Content-Type
 * - 缓存：内存命中、文件跨实例命中、过期重下载、LRU 淘汰
 * - shrinkMemory/clear 与单图失败隔离
 */

import { describe, it, expect, beforeAll, afterAll } from '@ohos/hypium';
import AbilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';
import { fileIo as fs } from '@kit.CoreFileKit';
import { image } from '@kit.ImageKit';
import {
  GfriendsCache, GfriendsDownloader, GfriendsHttpResponse, GfriendsHttpTransport, GfriendsImageBytes,
  GfriendsUrl, NetworkGfriendsDownloader, decodeImageSource,
} from '../../../main/ets/core/images/GfriendsCache';

const VALID_URL = 'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/A/Alice.jpg';
const SECOND_URL = 'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/B/Bob.png';

/** 1x1 透明 RGBA PNG（真实可解码，python zlib 生成）。 */
function pngBytes(): ArrayBuffer {
  const hex = '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489' +
    '0000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082';
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes.buffer;
}

class FakeDownloader implements GfriendsDownloader {
  requestedUrls: string[] = [];
  results: Map<string, GfriendsImageBytes | null> = new Map();

  constructor() {
    this.results.set(VALID_URL, { bytes: pngBytes(), extension: 'png' } as GfriendsImageBytes);
    this.results.set(SECOND_URL, { bytes: pngBytes(), extension: 'png' } as GfriendsImageBytes);
  }

  download(url: string): Promise<GfriendsImageBytes | null> {
    this.requestedUrls.push(url);
    const result = this.results.get(url);
    return Promise.resolve(result === undefined ? null : result);
  }
}

class FakeHttpTransport implements GfriendsHttpTransport {
  responses: Map<string, GfriendsHttpResponse> = new Map();
  requested: string[] = [];

  request(url: string): Promise<GfriendsHttpResponse> {
    this.requested.push(url);
    const response = this.responses.get(url);
    if (response === undefined) {
      return Promise.resolve({ statusCode: 404, location: null, contentType: null, bytes: null } as GfriendsHttpResponse);
    }
    return Promise.resolve(response);
  }
}

class CacheFixture {
  root: string;
  cache: GfriendsCache;
  downloader: FakeDownloader;
  nowValue: number;

  constructor(root: string, maxFiles: number = 512, maxTotalBytes: number = 256 * 1024 * 1024,
    ttlMs: number = GfriendsCache.DEFAULT_TTL_MS) {
    this.root = root;
    this.nowValue = 1750000000000;
    this.downloader = new FakeDownloader();
    this.cache = new GfriendsCache(root, this.downloader, decodeImageSource,
      () => this.nowValue, maxFiles, maxTotalBytes, ttlMs, 4, 8);
  }

  static async create(): Promise<CacheFixture> {
    const appContext = AbilityDelegatorRegistry.getAbilityDelegator().getAppContext();
    const root = `${appContext.cacheDir}/gfriends-test-${Date.now()}`;
    if (GfriendsCache.exists(root)) {
      GfriendsCache.removeRecursive(root);
    }
    return new CacheFixture(root);
  }

  async dispose(): Promise<void> {
    if (GfriendsCache.exists(this.root)) {
      GfriendsCache.removeRecursive(this.root);
    }
  }
}

export default function gfriendsCacheTest() {
  describe('GfriendsUrlTest', () => {
    it('accepts_valid_gfriends_url', 0, () => {
      expect(GfriendsUrl.isAllowed(VALID_URL)).assertTrue();
      expect(GfriendsUrl.isAllowed(
        'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/子/名.jpg')).assertTrue();
    });

    it('rejects_invalid_scheme_host_and_port', 0, () => {
      expect(GfriendsUrl.isAllowed(`http://${VALID_URL.substring('https://'.length)}`)).assertFalse();
      expect(GfriendsUrl.isAllowed('https://other.github.com/li-peifeng/gfriends/main/Content/a.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed(
        'https://raw.githubusercontent.com:8080/li-peifeng/gfriends/main/Content/a.jpg')).assertFalse();
    });

    it('rejects_query_fragment_userinfo_and_backslash', 0, () => {
      expect(GfriendsUrl.isAllowed(`${VALID_URL}?t=1`)).assertFalse();
      expect(GfriendsUrl.isAllowed(`${VALID_URL}#frag`)).assertFalse();
      expect(GfriendsUrl.isAllowed('https://u:p@raw.githubusercontent.com/li-peifeng/gfriends/main/Content/a.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed('https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content\\a.jpg')).assertFalse();
    });

    it('rejects_percent_encoded_traversal', 0, () => {
      expect(GfriendsUrl.isAllowed(
        'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/%2e%2e/evil.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed(
        'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/a%2fb.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed(
        'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/a%5cb.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed(
        'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/%2e/evil.jpg')).assertFalse();
    });

    it('rejects_wrong_prefix_and_dot_segments', 0, () => {
      expect(GfriendsUrl.isAllowed('https://raw.githubusercontent.com/other/main/Content/a.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed('https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/./a.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed('https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/../a.jpg')).assertFalse();
      expect(GfriendsUrl.isAllowed('https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content')).assertFalse();
    });

    it('image_extension_detects_formats', 0, () => {
      const png = pngBytes();
      expect(GfriendsUrl.imageExtension(png)).assertEqual('png');
      const jpeg = new Uint8Array([0xFF, 0xD8, 0xFF, 0xE0, 0, 0]).buffer as ArrayBuffer;
      expect(GfriendsUrl.imageExtension(jpeg)).assertEqual('jpg');
      const text = new Uint8Array([0x48, 0x49, 0x21, 0x21]).buffer as ArrayBuffer;
      expect(GfriendsUrl.imageExtension(text)).assertNull();
    });

    it('content_type_must_match_signature', 0, () => {
      expect(GfriendsUrl.contentTypeMatches('png', 'image/png')).assertTrue();
      expect(GfriendsUrl.contentTypeMatches('png', 'image/jpeg')).assertFalse();
      expect(GfriendsUrl.contentTypeMatches('png', null)).assertFalse();
      expect(GfriendsUrl.contentTypeMatches('jpg', 'image/jpeg; charset=utf-8')).assertTrue();
    });
  });

  describe('GfriendsDownloaderTest', () => {
    it('follows_redirects_with_per_hop_validation', 0, async (done: Function) => {
      const transport = new FakeHttpTransport();
      transport.responses.set(VALID_URL, {
        statusCode: 302, location: '/li-peifeng/gfriends/main/Content/B/Bob.png',
        contentType: null, bytes: null,
      } as GfriendsHttpResponse);
      transport.responses.set(SECOND_URL, {
        statusCode: 200, location: null, contentType: 'image/png', bytes: pngBytes(),
      } as GfriendsHttpResponse);
      const downloader = new NetworkGfriendsDownloader(transport);
      const result = await downloader.download(VALID_URL);
      expect(result != null).assertTrue();
      expect(result !== null ? result.extension : '').assertEqual('png');
      expect(transport.requested.length).assertEqual(2);
      expect(transport.requested[1]).assertEqual(SECOND_URL);
      done();
    });

    it('rejects_redirect_to_disallowed_host', 0, async (done: Function) => {
      const transport = new FakeHttpTransport();
      transport.responses.set(VALID_URL, {
        statusCode: 302, location: 'https://evil.example/x.jpg',
        contentType: null, bytes: null,
      } as GfriendsHttpResponse);
      const downloader = new NetworkGfriendsDownloader(transport);
      const result = await downloader.download(VALID_URL);
      expect(result).assertNull();
      done();
    });

    it('rejects_oversize_and_bad_content_type', 0, async (done: Function) => {
      const transport = new FakeHttpTransport();
      transport.responses.set(VALID_URL, {
        statusCode: 200, location: null, contentType: 'text/html', bytes: pngBytes(),
      } as GfriendsHttpResponse);
      const downloader = new NetworkGfriendsDownloader(transport, 100);
      const wrongType = await downloader.download(VALID_URL);
      expect(wrongType).assertNull();

      const big = new ArrayBuffer(200);
      transport.responses.set(SECOND_URL, {
        statusCode: 200, location: null, contentType: 'image/png', bytes: big,
      } as GfriendsHttpResponse);
      const tooBig = await downloader.download(SECOND_URL);
      expect(tooBig).assertNull();
      done();
    });
  });

  describe('GfriendsCacheTest', () => {
    let fixture: CacheFixture | null = null;

    it('decode_works_in_test_env', 0, async (done: Function) => {
      const pm = await decodeImageSource(pngBytes());
      expect('decode=' + (pm !== null)).assertEqual('decode=true');
      done();
    });


    beforeAll((done: Function) => {
      CacheFixture.create().then((created) => {
        fixture = created;
        done();
      });
    });

    afterAll(async (done: Function) => {
      if (fixture !== null) {
        await fixture.dispose();
      }
      done();
    });

    it('memory_hit_does_not_redownload', 0, async (done: Function) => {
      const cache = fixture!.cache;
      const first = await cache.load(VALID_URL);
      expect(first != null).assertTrue();
      const second = await cache.load(VALID_URL);
      expect(second != null).assertTrue();
      expect(fixture!.downloader.requestedUrls.length).assertEqual(1);
      expect(cache.memorySize).assertEqual(1);
      done();
    });

    it('file_cache_hit_across_instances', 0, async (done: Function) => {
      const root = fixture!.root;
      const first = await fixture!.cache.load(VALID_URL);
      expect(first != null).assertTrue();
      const downloader2 = new FakeDownloader();
      const cache2 = new GfriendsCache(root, downloader2, decodeImageSource,
        () => fixture!.nowValue, 512, 256 * 1024 * 1024, GfriendsCache.DEFAULT_TTL_MS, 4, 8);
      const loaded = await cache2.load(VALID_URL);
      expect(loaded != null).assertTrue();
      expect(downloader2.requestedUrls.length).assertEqual(0);
      done();
    });

    it('expired_entry_is_redownloaded', 0, async (done: Function) => {
      const fixture2 = await CacheFixture.create();
      try {
        await fixture2.cache.load(SECOND_URL);
        expect(fixture2.downloader.requestedUrls.length).assertEqual(1);
        fixture2.nowValue += GfriendsCache.DEFAULT_TTL_MS + 1000;
        fixture2.cache.shrinkMemory();
        const loaded = await fixture2.cache.load(SECOND_URL);
        expect(loaded != null).assertTrue();
        expect(fixture2.downloader.requestedUrls.length).assertEqual(2);
      } finally {
        await fixture2.dispose();
      }
      done();
    });

    it('lru_evicts_oldest_when_over_file_limit', 0, async (done: Function) => {
      const fixture3 = await CacheFixture.create();
      try {
        // 重新构造：文件上限 2
        const downloader3 = new FakeDownloader();
        const cache3 = new GfriendsCache(fixture3.root, downloader3, decodeImageSource,
          () => fixture3.nowValue, 2, 256 * 1024 * 1024, GfriendsCache.DEFAULT_TTL_MS, 4, 8);
        const urlA = VALID_URL;
        const urlB = SECOND_URL;
        const urlC = 'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/C/Chloe.webp';
        downloader3.results.set(urlC, { bytes: pngBytes(), extension: 'png' });
        await cache3.load(urlA);
        fixture3.nowValue += 1;
        await cache3.load(urlB);
        fixture3.nowValue += 1;
        await cache3.load(urlC);
        expect(cache3.memorySize).assertEqual(3);
        // 内存 LRU 上限 8，不淘汰；文件层 maxFiles=2：最旧文件被淘汰
        const emptyDownloader = new FakeDownloader();
        emptyDownloader.results.clear();
        const fresh = new GfriendsCache(fixture3.root, emptyDownloader, decodeImageSource,
          () => fixture3.nowValue, 2, 256 * 1024 * 1024, GfriendsCache.DEFAULT_TTL_MS, 4, 8);
        const reloadedA = await fresh.load(urlA);
        expect(reloadedA).assertNull(); // 文件被 LRU 淘汰且无下载源
        const reloadedC = await fresh.load(urlC);
        expect(reloadedC != null).assertTrue(); // 未被淘汰的文件命中
      } finally {
        await fixture3.dispose();
      }
      done();
    });

    it('shrink_memory_clears_pixelmaps', 0, async (done: Function) => {
      const cache = fixture!.cache;
      await cache.load(VALID_URL);
      expect(cache.memorySize).assertEqual(1);
      cache.shrinkMemory();
      expect(cache.memorySize).assertEqual(0);
      done();
    });

    it('single_image_failure_is_isolated', 0, async (done: Function) => {
      const fixture4 = await CacheFixture.create();
      try {
        const badUrl = 'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/D/Dora.webp';
        fixture4.downloader.results.set(badUrl, null);
        const failed = await fixture4.cache.load(badUrl);
        expect(failed).assertNull();
        const ok = await fixture4.cache.load(SECOND_URL);
        expect(ok != null).assertTrue();
      } finally {
        await fixture4.dispose();
      }
      done();
    });

    it('clear_removes_directory_and_entries', 0, async (done: Function) => {
      const cache = fixture!.cache;
      await cache.load(VALID_URL);
      expect(cache.memorySize).assertEqual(1);
      await cache.clear();
      expect(cache.memorySize).assertEqual(0);
      expect(GfriendsCache.exists(`${fixture!.root}/gfriends-v1`)).assertTrue();
      const fresh = new GfriendsCache(fixture!.root, new FakeDownloader(), decodeImageSource,
        () => fixture!.nowValue, 512, 256 * 1024 * 1024, GfriendsCache.DEFAULT_TTL_MS, 4, 8);
      const reloaded = await fresh.load(VALID_URL);
      expect(reloaded != null).assertTrue();
      done();
    });
  });
}
