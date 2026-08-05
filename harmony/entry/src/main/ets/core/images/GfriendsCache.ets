/**
 * GFriends 私有图片缓存（AC-051/052/053）。
 *
 * - 只信任后端唯一匹配 URL（逐字段白名单），客户端不做歧义匹配。
 * - 匿名下载（不复用认证 ApiClient，无 Authorization/Cookie）；8 MiB、
 *   3 重定向逐跳校验、JPEG/PNG/WebP 签名 + Content-Type。
 * - 文件 LRU：cacheDir/gfriends-v1 + index.json（512 文件/256 MiB/7 天滑动，
 *   临时文件原子替换，启动整理并清理孤立文件）。
 * - 内存 LRU：PixelMap 按需解码（ImageSource），onMemoryLevel 缩减。
 * - single-flight + 固定并发；单图失败隔离（返回 null，不影响其他图片）。
 * - 图片生命周期与媒体库永久图片分离：本缓存位于应用 cacheDir（临时），
 *   logout 时证明式清理（目录名精确匹配 gfriends-v1）。
 */

import { http } from '@kit.NetworkKit';
import { fileIo as fs } from '@kit.CoreFileKit';
import { image } from '@kit.ImageKit';
import { url as urlKit, util } from '@kit.ArkTS';

/** GFriends URL 白名单（与 Windows gfriends_url.dart 语义一致）。 */
export class GfriendsUrl {
  static readonly PREFIX: string[] = ['li-peifeng', 'gfriends', 'main', 'Content'];

  static isAllowed(url: string): boolean {
    if (url.includes('\\')) {
      return false;
    }
    // URL 解析会折叠字面 . 与 .. 段；编码形态（%2e/%2f/%5c）在此拒绝
    if (url.includes('/./') || url.includes('/../') || url.endsWith('/.') || url.endsWith('/..')) {
      return false;
    }
    const encoded = url.toLowerCase();
    if (encoded.includes('%2e') || encoded.includes('%2f') || encoded.includes('%5c')) {
      return false;
    }
    let parsed: urlKit.URL;
    try {
      parsed = new urlKit.URL(url);
    } catch (err) {
      return false;
    }
    if (parsed.protocol !== 'https:' ||
      parsed.hostname !== 'raw.githubusercontent.com' ||
      (parsed.port.length > 0 && parsed.port !== '443') ||
      parsed.username.length > 0 ||
      parsed.search.length > 0 ||
      parsed.hash.length > 0) {
      return false;
    }
    const segments = parsed.pathname.split('/').filter((seg: string) => seg.length > 0);
    if (segments.length <= GfriendsUrl.PREFIX.length) {
      return false;
    }
    for (let i = 0; i < GfriendsUrl.PREFIX.length; i++) {
      if (segments[i] !== GfriendsUrl.PREFIX[i]) {
        return false;
      }
    }
    for (let i = GfriendsUrl.PREFIX.length; i < segments.length; i++) {
      // pathname 为编码形态：解码后校验（%2e→.、%2f→/、%5c→\ 均被拒绝；中文正常）
      let seg = segments[i];
      try {
        seg = decodeURIComponent(seg);
      } catch (err) {
        return false;
      }
      if (seg.length === 0 || seg === '.' || seg === '..' || seg.includes('/') || seg.includes('\\')) {
        return false;
      }
    }
    return true;
  }

  /** 解析重定向 Location（相对/绝对），失败返回 null。 */
  static resolveLocation(current: string, location: string): string | null {
    try {
      return new urlKit.URL(location, current).href;
    } catch (err) {
      return null;
    }
  }

  /** 按文件签名识别 jpg/png/webp；非法返回 null。 */
  static imageExtension(buffer: ArrayBuffer): string | null {
    const bytes = new Uint8Array(buffer);
    if (bytes.length >= 3 && bytes[0] === 0xFF && bytes[1] === 0xD8 && bytes[2] === 0xFF) {
      return 'jpg';
    }
    if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4E &&
      bytes[3] === 0x47 && bytes[4] === 0x0D && bytes[5] === 0x0A && bytes[6] === 0x1A &&
      bytes[7] === 0x0A) {
      return 'png';
    }
    if (bytes.length >= 12 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 &&
      bytes[3] === 0x46 && bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 &&
      bytes[11] === 0x50) {
      return 'webp';
    }
    return null;
  }

  /** Content-Type 与签名扩展匹配；contentType 为 null 时拒绝（契约要求）。 */
  static contentTypeMatches(extension: string, contentType: string | null): boolean {
    if (contentType === null) {
      return false;
    }
    const mediaType = contentType.split(';')[0].trim().toLowerCase();
    if (extension === 'jpg') {
      return mediaType === 'image/jpeg';
    }
    if (extension === 'png') {
      return mediaType === 'image/png';
    }
    if (extension === 'webp') {
      return mediaType === 'image/webp';
    }
    return false;
  }
}

/** 下载响应（传输层抽象，便于测试注入）。 */
export interface GfriendsHttpResponse {
  readonly statusCode: number;
  readonly location: string | null;
  readonly contentType: string | null;
  readonly bytes: ArrayBuffer | null;
}

export interface GfriendsHttpTransport {
  request(url: string): Promise<GfriendsHttpResponse>;
}

/** 生产传输：Network Kit http，匿名，二进制，手动重定向（maxRedirects=0）。 */
export class NetworkGfriendsHttpTransport implements GfriendsHttpTransport {
  private readonly connectTimeoutMs: number;
  private readonly readTimeoutMs: number;

  constructor(connectTimeoutMs: number = 10000, readTimeoutMs: number = 30000) {
    this.connectTimeoutMs = connectTimeoutMs;
    this.readTimeoutMs = readTimeoutMs;
  }

  async request(url: string): Promise<GfriendsHttpResponse> {
    const client = http.createHttp();
    try {
      const response = await client.request(url, {
        method: http.RequestMethod.GET,
        header: { 'Accept': 'image/jpeg, image/png, image/webp' },
        expectDataType: http.HttpDataType.ARRAY_BUFFER,
        connectTimeout: this.connectTimeoutMs,
        readTimeout: this.readTimeoutMs,
        maxRedirects: 0,
      });
      const headers = response.header as Record<string, Object>;
      const headerValue = (key: string): string | null => {
        const value = headers[key];
        if (value === undefined || value === null) {
          return null;
        }
        return String(value);
      };
      const raw = response.result;
      const bytes = raw instanceof ArrayBuffer ? raw : null;
      return {
        statusCode: response.responseCode,
        location: headerValue('location') ?? headerValue('Location'),
        contentType: headerValue('content-type') ?? headerValue('Content-Type'),
        bytes: bytes,
      };
    } catch (err) {
      return { statusCode: 0, location: null, contentType: null, bytes: null };
    } finally {
      client.destroy();
    }
  }
}

/** 下载结果（已通过签名与 Content-Type 校验）。 */
export interface GfriendsImageBytes {
  readonly bytes: ArrayBuffer;
  readonly extension: string;
}

/** 下载器：逐跳白名单校验 + 3 重定向 + 8 MiB + 签名/Content-Type。 */
export interface GfriendsDownloader {
  download(url: string): Promise<GfriendsImageBytes | null>;
}

export class NetworkGfriendsDownloader implements GfriendsDownloader {
  private readonly transport: GfriendsHttpTransport;
  private readonly maxImageBytes: number;

  constructor(transport: GfriendsHttpTransport, maxImageBytes: number = 8 * 1024 * 1024) {
    this.transport = transport;
    this.maxImageBytes = maxImageBytes;
  }

  async download(url: string): Promise<GfriendsImageBytes | null> {
    let current = url;
    let redirects = 0;
    while (true) {
      if (!GfriendsUrl.isAllowed(current)) {
        return null;
      }
      const response = await this.transport.request(current);
      const status = response.statusCode;
      if (status === 301 || status === 302 || status === 303 || status === 307 || status === 308) {
        if (redirects >= 3 || response.location === null || response.location.length === 0) {
          return null;
        }
        const next = GfriendsUrl.resolveLocation(current, response.location);
        if (next === null || !GfriendsUrl.isAllowed(next)) {
          return null;
        }
        current = next;
        redirects++;
        continue;
      }
      if (status !== 200 || response.bytes === null) {
        return null;
      }
      const bytes = response.bytes;
      if (bytes.byteLength === 0 || bytes.byteLength > this.maxImageBytes) {
        return null;
      }
      const extension = GfriendsUrl.imageExtension(bytes);
      if (extension === null || !GfriendsUrl.contentTypeMatches(extension, response.contentType)) {
        return null;
      }
      return { bytes: bytes, extension: extension };
    }
  }
}

/** 内存/文件缓存条目（索引持久化）。 */
class CacheEntry {
  readonly url: string;
  readonly fileId: string;
  readonly byteSize: number;
  readonly extension: string;
  readonly lastAccessedAt: number;

  constructor(url: string, fileId: string, byteSize: number, extension: string, lastAccessedAt: number) {
    this.url = url;
    this.fileId = fileId;
    this.byteSize = byteSize;
    this.extension = extension;
    this.lastAccessedAt = lastAccessedAt;
  }
}

/** PixelMap 解码器（生产用 ImageSource；测试注入 fake）。 */
export type PixelMapDecoder = (bytes: ArrayBuffer) => Promise<image.PixelMap | null>;

const FILE_ID_PATTERN: RegExp = /^[0-9a-f]{32}$/;

/**
 * 有界 GFriends 图片缓存。
 * 构造参数全部可注入（目录/下载器/时钟/解码器/上限），默认生产配置。
 */
export class GfriendsCache {
  static readonly DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024;
  static readonly DEFAULT_MAX_FILES = 512;
  static readonly DEFAULT_MAX_TOTAL_BYTES = 256 * 1024 * 1024;
  static readonly DEFAULT_TTL_MS = 7 * 24 * 3600 * 1000;
  static readonly DEFAULT_MAX_CONCURRENT = 4;
  static readonly DEFAULT_MEMORY_LIMIT = 64;
  static readonly DIR_NAME = 'gfriends-v1';

  private readonly cacheRoot: string;
  private readonly directory: string;
  private readonly downloader: GfriendsDownloader;
  private readonly now: () => number;
  private readonly decode: PixelMapDecoder;
  private readonly maxFiles: number;
  private readonly maxTotalBytes: number;
  private readonly ttlMs: number;
  private readonly maxConcurrent: number;
  private readonly memoryLimit: number;
  private readonly idFactory: () => string;

  private entries: Map<string, CacheEntry> = new Map();
  private memoryLru: Map<string, image.PixelMap> = new Map();
  private generation: number = 0;
  private lastIndexWriteAt: number = 0;
  private inFlight: Map<string, Promise<image.PixelMap | null>> = new Map();
  private activeDownloads: number = 0;
  private readonly waiters: (() => void)[] = [];
  private initialized: boolean = false;

  /** 构造：cacheRoot 为应用 cacheDir（cacheRoot 与目录名共同证明清理目标）。 */
  constructor(cacheRoot: string, downloader: GfriendsDownloader, decode: PixelMapDecoder, now: () => number,
    maxFiles: number = GfriendsCache.DEFAULT_MAX_FILES, maxTotalBytes: number = GfriendsCache.DEFAULT_MAX_TOTAL_BYTES,
    ttlMs: number = GfriendsCache.DEFAULT_TTL_MS, maxConcurrent: number = GfriendsCache.DEFAULT_MAX_CONCURRENT,
    memoryLimit: number = GfriendsCache.DEFAULT_MEMORY_LIMIT) {
    this.cacheRoot = cacheRoot;
    this.directory = `${cacheRoot}/${GfriendsCache.DIR_NAME}`;
    this.downloader = downloader;
    this.decode = decode;
    this.now = now;
    this.maxFiles = maxFiles;
    this.maxTotalBytes = maxTotalBytes;
    this.ttlMs = ttlMs;
    this.maxConcurrent = maxConcurrent;
    this.memoryLimit = memoryLimit;
    this.idFactory = GfriendsCache.randomId;
  }

  get dirPath(): string {
    return this.directory;
  }

  /** 加载图片：内存 LRU → 文件缓存 → 下载；任何失败返回 null（单图隔离）。 */
  load(url: string): Promise<image.PixelMap | null> {
    if (!GfriendsUrl.isAllowed(url)) {
      return Promise.resolve(null);
    }
    const existing = this.inFlight.get(url);
    if (existing !== undefined) {
      return existing;
    }
    const promise = this.loadInternal(url);
    this.inFlight.set(url, promise);
    promise.then(() => {
      if (this.inFlight.get(url) === promise) {
        this.inFlight.delete(url);
      }
    }).catch(() => {
      if (this.inFlight.get(url) === promise) {
        this.inFlight.delete(url);
      }
    });
    return promise;
  }

  private async loadInternal(url: string): Promise<image.PixelMap | null> {
    const memory = this.memoryLru.get(url);
    if (memory !== undefined) {
      this.touchMemory(url);
      return memory;
    }
    try {
      this.ensureInitialized();
    } catch (err) {
      return null;
    }
    const fileBytes = this.readCachedFile(url);
    if (fileBytes !== null) {
      const decoded = await this.safeDecode(fileBytes.bytes);
      if (decoded !== null) {
        this.putMemory(url, decoded);
        return decoded;
      }
      this.removeEntry(url);
    }
    const gen = this.generation;
    const permit = await this.acquirePermit();
    try {
      const imageBytes = await this.downloader.download(url);
      if (imageBytes === null || imageBytes.bytes.byteLength > GfriendsCache.DEFAULT_MAX_IMAGE_BYTES) {
        return null;
      }
      const decoded = await this.safeDecode(imageBytes.bytes);
      if (decoded === null) {
        return null;
      }
      // clear/shrink 后在途结果丢弃：不写缓存、不占内存
      if (gen !== this.generation) {
        return null;
      }
      this.storeFile(url, imageBytes);
      this.putMemory(url, decoded);
      return decoded;
    } finally {
      this.releasePermit();
    }
  }

  private async safeDecode(bytes: ArrayBuffer): Promise<image.PixelMap | null> {
    try {
      return await this.decode(bytes);
    } catch (err) {
      return null;
    }
  }

  // ---- 内存 LRU ----

  private touchMemory(url: string): void {
    const value = this.memoryLru.get(url);
    if (value === undefined) {
      return;
    }
    this.memoryLru.delete(url);
    this.memoryLru.set(url, value);
  }

  private putMemory(url: string, pixelMap: image.PixelMap): void {
    const existing = this.memoryLru.get(url);
    if (existing !== undefined) {
      this.memoryLru.delete(url);
      existing.release().catch(() => {
      });
    }
    this.memoryLru.set(url, pixelMap);
    while (this.memoryLru.size > this.memoryLimit) {
      const keys = Array.from(this.memoryLru.keys());
      if (keys.length === 0) {
        break;
      }
      const oldestKey = keys[0];
      const oldest = this.memoryLru.get(oldestKey);
      this.memoryLru.delete(oldestKey);
      if (oldest !== undefined) {
        oldest.release().catch(() => {
        });
      }
    }
  }

  /** 低内存回调：清空内存 PixelMap 缓存。 */
  shrinkMemory(): void {
    this.generation++;
    for (const key of Array.from(this.memoryLru.keys())) {
      const value = this.memoryLru.get(key);
      this.memoryLru.delete(key);
      if (value !== undefined) {
        value.release().catch(() => {
        });
      }
    }
  }

  get memorySize(): number {
    return this.memoryLru.size;
  }

  // ---- 文件缓存 ----

  private ensureInitialized(): void {
    if (this.initialized) {
      return;
    }
    if (!GfriendsCache.exists(this.directory)) {
      try {
        fs.mkdirSync(this.directory, true);
      } catch (err) {
        // 目录已存在（13900002）或创建失败：后续写入按需重建
      }
    }
    const indexPath = `${this.directory}/index.json`;
    if (GfriendsCache.exists(indexPath)) {
      try {
        const text = fs.readTextSync(indexPath);
        const parsed = JSON.parse(text) as Record<string, Object>;
        if (parsed['version'] !== 1) {
          // version 必须是 1；错误版本重建
          throw new Error('invalid index version');
        }
        const rawEntries = parsed['entries'] as Object[];
        if (!Array.isArray(rawEntries)) {
          throw new Error('invalid index entries');
        }
        const loaded: Map<string, CacheEntry> = new Map();
        for (const raw of rawEntries) {
          const entry = GfriendsCache.parseEntry(raw as Record<string, Object>);
          if (loaded.has(entry.url)) {
            throw new Error('duplicate cache url');
          }
          loaded.set(entry.url, entry);
        }
        this.entries = loaded;
      } catch (err) {
        this.resetDirectory();
      }
    }
    this.pruneInternal();
    this.writeIndex();
    this.initialized = true;
  }

  private readCachedFile(url: string): GfriendsImageBytes | null {
    const entry = this.entries.get(url);
    if (entry === undefined) {
      return null;
    }
    if (this.now() - entry.lastAccessedAt > this.ttlMs) {
      this.removeEntry(url);
      return null;
    }
    const path = this.filePath(entry);
    if (!GfriendsCache.exists(path)) {
      this.removeEntry(url);
      return null;
    }
    const stat = fs.statSync(path);
    if (stat.size !== entry.byteSize) {
      this.removeEntry(url);
      return null;
    }
    try {
      const fd = fs.openSync(path, fs.OpenMode.READ_ONLY);
      let buffer: ArrayBuffer;
      try {
        buffer = new ArrayBuffer(stat.size);
        fs.readSync(fd.fd, buffer);
      } finally {
        fs.closeSync(fd.fd);
      }
      if (GfriendsUrl.imageExtension(buffer) !== entry.extension) {
        this.removeEntry(url);
        return null;
      }
      this.entries.set(url, new CacheEntry(entry.url, entry.fileId, entry.byteSize, entry.extension, this.now()));
      this.throttledIndexWrite();
      return { bytes: buffer, extension: entry.extension };
    } catch (err) {
      this.removeEntry(url);
      return null;
    }
  }

  private storeFile(url: string, imageBytes: GfriendsImageBytes): void {
    try {
      this.ensureDirectory();
      const fileId = this.idFactory();
      if (!FILE_ID_PATTERN.test(fileId)) {
        return;
      }
      const entry = new CacheEntry(url, fileId, imageBytes.bytes.byteLength, imageBytes.extension, this.now());
      const temporary = `${this.directory}/.${fileId}.tmp`;
      const target = this.filePath(entry);
      try {
        const fd = fs.openSync(temporary, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
        try {
          fs.writeSync(fd.fd, imageBytes.bytes);
        } finally {
          fs.closeSync(fd.fd);
        }
        fs.renameSync(temporary, target);
      } catch (err) {
        if (GfriendsCache.exists(temporary)) {
          fs.unlinkSync(temporary);
        }
        return;
      }
      const replaced = this.entries.get(url);
      this.entries.set(url, entry);
      if (replaced !== undefined && replaced.fileId !== entry.fileId) {
        const oldPath = this.filePath(replaced);
        if (GfriendsCache.exists(oldPath)) {
          fs.unlinkSync(oldPath);
        }
      }
      this.pruneInternal();
      this.writeIndex();
    } catch (err) {
      // 写缓存失败不影响图片显示（内存 LRU 已持有）
    }
  }

  private removeEntry(url: string): void {
    const entry = this.entries.get(url);
    if (entry === undefined) {
      return;
    }
    this.entries.delete(url);
    const path = this.filePath(entry);
    try {
      if (GfriendsCache.exists(path)) {
        fs.unlinkSync(path);
      }
    } catch (err) {
      // 忽略单文件删除失败
    }
  }

  private pruneInternal(): void {
    const now = this.now();
    for (const url of Array.from(this.entries.keys())) {
      const entry = this.entries.get(url);
      if (entry === undefined) {
        continue;
      }
      const path = this.filePath(entry);
      if (now - entry.lastAccessedAt > this.ttlMs || !GfriendsCache.exists(path)) {
        this.entries.delete(url);
        try {
          if (GfriendsCache.exists(path)) {
            fs.unlinkSync(path);
          }
        } catch (err) {
          // 忽略
        }
      }
    }
    // LRU：按 lastAccessedAt 升序淘汰直到文件数与总字节不超上限
    const ordered = Array.from(this.entries.values());
    ordered.sort((a: CacheEntry, b: CacheEntry) => {
      if (a.lastAccessedAt !== b.lastAccessedAt) {
        return a.lastAccessedAt - b.lastAccessedAt;
      }
      return a.fileId < b.fileId ? -1 : (a.fileId > b.fileId ? 1 : 0);
    });
    let totalBytes = 0;
    for (const entry of this.entries.values()) {
      totalBytes += entry.byteSize;
    }
    for (const entry of ordered) {
      if (this.entries.size <= this.maxFiles && totalBytes <= this.maxTotalBytes) {
        break;
      }
      const removed = this.entries.get(entry.url);
      if (removed === undefined) {
        continue;
      }
      this.entries.delete(entry.url);
      totalBytes -= removed.byteSize;
      const path = this.filePath(removed);
      try {
        if (GfriendsCache.exists(path)) {
          fs.unlinkSync(path);
        }
      } catch (err) {
        // 忽略
      }
    }
    // 清理不在索引中的孤立文件（index.json 与条目文件除外）
    try {
      if (GfriendsCache.exists(this.directory)) {
        const referenced: string[] = [`${this.directory}/index.json`];
        for (const entry of this.entries.values()) {
          referenced.push(this.filePath(entry));
        }
        for (const name of fs.listFileSync(this.directory)) {
          const path = `${this.directory}/${name}`;
          if (!referenced.includes(path) && !fs.statSync(path).isDirectory()) {
            try {
              fs.unlinkSync(path);
            } catch (err) {
              // 忽略
            }
          }
        }
      }
    } catch (err) {
      // 忽略孤立清理失败
    }
  }

  /** 限流写索引：命中刷新不频繁落盘（写放大控制）。 */
  private throttledIndexWrite(): void {
    if (this.now() - this.lastIndexWriteAt < 60000) {
      return;
    }
    this.writeIndex();
  }

  private writeIndex(): void {
    try {
      this.ensureDirectory();
      const entriesJson: Record<string, Object>[] = [];
      const ordered = Array.from(this.entries.values());
      ordered.sort((a: CacheEntry, b: CacheEntry) => (a.fileId < b.fileId ? -1 : (a.fileId > b.fileId ? 1 : 0)));
      for (const entry of ordered) {
        entriesJson.push({
          'url': entry.url, 'file_id': entry.fileId, 'byte_size': entry.byteSize,
          'extension': entry.extension, 'last_accessed_at': entry.lastAccessedAt,
        });
      }
      const index = JSON.stringify({ 'version': 1, 'entries': entriesJson });
      const temporary = `${this.directory}/.index.tmp`;
      const target = `${this.directory}/index.json`;
      const fd = fs.openSync(temporary, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
      try {
        fs.writeSync(fd.fd, index);
      } finally {
        fs.closeSync(fd.fd);
      }
      fs.renameSync(temporary, target);
      this.lastIndexWriteAt = this.now();
    } catch (err) {
      // 索引写失败：下次启动重建
    }
  }

  /** 证明式清理：仅删除 cacheRoot 下名为 gfriends-v1 的目录。 */
  async clear(): Promise<void> {
    this.generation++;
    this.shrinkMemory();
    this.entries.clear();
    this.initialized = false;
    const expected = `${this.cacheRoot}/${GfriendsCache.DIR_NAME}`;
    if (this.directory !== expected) {
      return;
    }
    if (!GfriendsCache.exists(this.directory)) {
      return;
    }
    try {
      GfriendsCache.removeRecursive(this.directory);
    } catch (err) {
      // 清理失败不阻塞 logout
    }
    try {
      fs.mkdirSync(this.directory);
    } catch (err) {
      // 目录重建失败：后续写入按需重建
    }
  }

  private ensureDirectory(): void {
    if (!GfriendsCache.exists(this.directory)) {
      try {
        fs.mkdirSync(this.directory, true);
      } catch (err) {
        // 目录已存在（13900002）或创建失败：后续写入按需重建
      }
    }
  }

  private filePath(entry: CacheEntry): string {
    return `${this.directory}/${entry.fileId}.${entry.extension}`;
  }

  private resetDirectory(): void {
    this.entries.clear();
    try {
      if (GfriendsCache.exists(this.directory)) {
        GfriendsCache.removeRecursive(this.directory);
      }
    } catch (err) {
      // 忽略
    }
    try {
      fs.mkdirSync(this.directory);
    } catch (err) {
      // 忽略
    }
  }

  private async acquirePermit(): Promise<void> {
    if (this.activeDownloads < this.maxConcurrent) {
      this.activeDownloads++;
      return;
    }
    await new Promise<void>((resolve) => {
      this.waiters.push(resolve);
    });
    this.activeDownloads++;
  }

  private releasePermit(): void {
    this.activeDownloads--;
    const next = this.waiters.shift();
    if (next !== undefined) {
      next();
    }
  }

  // ---- 静态工具 ----

  private static parseEntry(raw: Record<string, Object>): CacheEntry {
    const url = raw['url'];
    const fileId = raw['file_id'];
    const byteSize = raw['byte_size'];
    const extension = raw['extension'];
    const lastAccessedAt = raw['last_accessed_at'];
    if (typeof url !== 'string' || !GfriendsUrl.isAllowed(url) ||
      typeof fileId !== 'string' || !FILE_ID_PATTERN.test(fileId) ||
      typeof byteSize !== 'number' || byteSize < 1 || byteSize > GfriendsCache.DEFAULT_MAX_IMAGE_BYTES ||
      typeof extension !== 'string' || !GfriendsCache.validExtension(extension) ||
      typeof lastAccessedAt !== 'number') {
      throw new Error('invalid cache entry');
    }
    return new CacheEntry(url, fileId, byteSize, extension, lastAccessedAt);
  }

  private static validExtension(extension: string): boolean {
    return extension === 'jpg' || extension === 'png' || extension === 'webp';
  }

  private static randomId(): string {
    return util.generateRandomUUID().replace(/-/g, '').substring(0, 32);
  }

  /** 存在性判断：statSync 优先，accessSync 兜底（API 24 目录行为差异）。 */
  static exists(path: string): boolean {
    try {
      fs.statSync(path);
      return true;
    } catch (err) {
      // statSync 不可靠时用 accessSync 复核
    }
    try {
      return fs.accessSync(path);
    } catch (err) {
      return false;
    }
  }

  /** API 24 fileIo 无递归删除：手动遍历目录树。 */
  static removeRecursive(path: string): void {
    const entries = fs.listFileSync(path);
    for (const name of entries) {
      const child = `${path}/${name}`;
      if (fs.statSync(child).isDirectory()) {
        GfriendsCache.removeRecursive(child);
      } else {
        fs.unlinkSync(child);
      }
    }
    fs.rmdirSync(path);
  }
}

/** 生产解码器：ImageSource 按需解码（返回 PixelMap）。 */
export async function decodeImageSource(bytes: ArrayBuffer): Promise<image.PixelMap | null> {
  try {
    const source = image.createImageSource(bytes);
    const pixelMap = await source.createPixelMap();
    source.release();
    return pixelMap;
  } catch (err) {
    return null;
  }
}

/**
 * 全局缓存持有者：cacheRoot 由 EntryAbilityStage 提供（应用 cacheDir），
 * onMemoryLevel 缩减内存；logout 证明式清理。测试直接构造 GfriendsCache。
 */
export class GfriendsCacheHolder {
  private cache: GfriendsCache | null = null;

  attach(cacheRoot: string): void {
    if (this.cache !== null) {
      return;
    }
    this.cache = new GfriendsCache(cacheRoot, new NetworkGfriendsDownloader(new NetworkGfriendsHttpTransport()),
      decodeImageSource, () => Date.now());
  }

  get cacheInstance(): GfriendsCache | null {
    return this.cache;
  }

  shrinkMemory(): void {
    if (this.cache !== null) {
      this.cache.shrinkMemory();
    }
  }

  async clear(): Promise<void> {
    if (this.cache !== null) {
      await this.cache.clear();
    }
  }
}

/** 全局 GFriends 缓存单例。 */
export const gfriendsCache = new GfriendsCacheHolder();
