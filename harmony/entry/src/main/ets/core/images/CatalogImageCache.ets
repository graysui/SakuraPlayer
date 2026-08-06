/**
 * 认证目录图片内存缓存与 URL 校验（AC-074 封面/剧照）。
 *
 * - 只接受 `/api/v1/catalog/images/{uuid}` 相对路径（严格 UUID 8-4-4-4-12）；
 *   绝对 URL、路径穿越、非图片 API 路径一律拒绝（返回 null，绝不发起请求）。
 * - 进程级内存 LRU（上限 64 张，认证图片按需加载，不做磁盘缓存）。
 * - 退出登录（AuthStore.logout）必须调用 clear()，不得跨会话复用旧图。
 */

import { image } from '@kit.ImageKit';
import { http } from '@kit.NetworkKit';
import { ApiClient } from '../api/ApiClient';

// 严格 UUID 8-4-4-4-12；只接受 /api/v1/catalog/images/{uuid} 相对路径
const CATALOG_IMAGE_PATTERN: RegExp =
  /^\/api\/v1\/catalog\/images\/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/;

/** URL 校验（可独立测试）。 */
export class CatalogImageUrl {
  /** 合法路径返回图片 ID，否则 null（不匹配/绝对 URL/非 catalog 路径）。 */
  static imageIdOf(path: string): string | null {
    if (path.startsWith('http://') || path.startsWith('https://')) {
      return null;
    }
    const match = CATALOG_IMAGE_PATTERN.exec(path);
    if (match === null) {
      return null;
    }
    return match[1];
  }
}

class CatalogEntry {
  readonly url: string;
  readonly pixelMap: image.PixelMap;
  lastAccessedAt: number;

  constructor(url: string, pixelMap: image.PixelMap) {
    this.url = url;
    this.pixelMap = pixelMap;
    this.lastAccessedAt = 0;
  }
}

/** 进程级内存 LRU 单例：认证图片按需加载，最多保留 64 张。 */
export class CatalogImageCache {
  private readonly entries: CatalogEntry[] = [];
  private readonly inflight: Map<string, Promise<image.PixelMap | null>> = new Map();
  static readonly MAX_ENTRIES = 64;

  /** 当前缓存图片数（测试/诊断用）。 */
  get size(): number {
    return this.entries.length;
  }

  /** 校验并加载；URL 非法或无客户端返回 null。 */
  async load(url: string, client: ApiClient | null): Promise<image.PixelMap | null> {
    if (CatalogImageUrl.imageIdOf(url) === null) {
      return null;
    }
    const cached = this.peek(url);
    if (cached !== null) {
      return cached;
    }
    const pending = this.inflight.get(url);
    if (pending !== undefined) {
      return pending;
    }
    if (client === null) {
      return null;
    }
    const promise = this.fetch(url, client);
    this.inflight.set(url, promise);
    try {
      return await promise;
    } finally {
      this.inflight.delete(url);
    }
  }

  /** 清空内存缓存（退出登录/认证变化时调用）。 */
  clear(): void {
    for (const entry of this.entries) {
      try {
        entry.pixelMap.release();
      } catch (err) {
        // 已释放的 PixelMap 忽略
      }
    }
    this.entries.splice(0, this.entries.length);
  }

  private async fetch(url: string, client: ApiClient): Promise<image.PixelMap | null> {
    const token = client.getAccessToken();
    const imageId = CatalogImageUrl.imageIdOf(url);
    if (token === null || imageId === null) {
      return null;
    }
    let pixelMap: image.PixelMap | null = null;
    let httpRequest: http.HttpRequest | null = null;
    let source: image.ImageSource | null = null;
    try {
      httpRequest = http.createHttp();
      // 用提取的 uuid 构造干净路径（cover_url 已含 /api/v1 前缀，避免双前缀）
      const response = await httpRequest.request(`${client.base}/catalog/images/${imageId}`, {
        method: http.RequestMethod.GET,
        expectDataType: http.HttpDataType.ARRAY_BUFFER,
        header: { 'Authorization': `Bearer ${token}` },
        connectTimeout: 10000,
        readTimeout: 30000,
      });
      const result = response.result;
      if (response.responseCode !== 200 || !(result instanceof ArrayBuffer)) {
        return null;
      }
      source = image.createImageSource(result);
      pixelMap = await source.createPixelMap();
      this.put(url, pixelMap);
      return pixelMap;
    } catch (err) {
      return null;
    } finally {
      if (source !== null) {
        try {
          source.release();
        } catch (releaseErr) {
          // 忽略释放异常
        }
      }
      if (httpRequest !== null) {
        httpRequest.destroy();
      }
    }
  }

  private peek(url: string): image.PixelMap | null {
    for (let i = 0; i < this.entries.length; i++) {
      const entry = this.entries[i];
      if (entry.url === url) {
        entry.lastAccessedAt = Date.now();
        // 移到末尾（最近使用）
        this.entries.splice(i, 1);
        this.entries.push(entry);
        return entry.pixelMap;
      }
    }
    return null;
  }

  private put(url: string, pixelMap: image.PixelMap): void {
    this.entries.push(new CatalogEntry(url, pixelMap));
    if (this.entries.length > CatalogImageCache.MAX_ENTRIES) {
      const oldest = this.entries.shift();
      if (oldest !== undefined) {
        try {
          oldest.pixelMap.release();
        } catch (err) {
          // 忽略释放异常
        }
      }
    }
  }
}

/** 全局认证图片缓存单例。 */
export const catalogImageCache = new CatalogImageCache();
