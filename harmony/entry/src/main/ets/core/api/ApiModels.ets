/**
 * SakuraPlayer OpenAPI 类型化 DTO 与 JSON 校验读取器。
 *
 * ArkTS strict：禁止 any/unknown 逃逸。所有 OpenAPI 响应都经 JsonReader
 * 逐字段校验，形状非法抛 ProtocolException（由 ApiClient 包装为
 * client_protocol_error）。
 */

/** 协议/形状错误（DTO 校验失败）。 */
export class ProtocolException extends Error {
  readonly reason: string;

  constructor(reason: string) {
    super(`protocol error: ${reason}`);
    this.reason = reason;
  }
}

/** 稳定错误码正则：^[a-z0-9_]+$。 */
const ERROR_CODE_PATTERN: RegExp = /^[a-z0-9_]+$/;

/** 后端 ApiError 载荷。 */
export class ApiErrorBody {
  readonly code: string;
  readonly message: string;
  readonly requestId: string;
  readonly details: string | null;

  constructor(code: string, message: string, requestId: string, details: string | null) {
    this.code = code;
    this.message = message;
    this.requestId = requestId;
    this.details = details;
  }

  static fromReader(reader: JsonReader): ApiErrorBody {
    const code = reader.string('code');
    if (!ERROR_CODE_PATTERN.test(code)) {
      throw new ProtocolException(`invalid error code: ${code}`);
    }
    const requestId = reader.optionalString('request_id') ?? '';
    const detailsRaw = reader.optionalObject('details');
    return new ApiErrorBody(code, reader.string('message'), requestId, detailsRaw === null ? null : JSON.stringify(detailsRaw));
  }
}

/** 客户端统一 API 异常。 */
export class ApiException extends Error {
  readonly code: string;
  readonly statusCode: number;
  readonly requestId: string;
  readonly details: string | null;

  constructor(code: string, statusCode: number, requestId: string, message: string, details: string | null) {
    super(message);
    this.code = code;
    this.statusCode = statusCode;
    this.requestId = requestId;
    this.details = details;
  }
}

/** 类型化 JSON 读取器。 */
export class JsonReader {
  private readonly data: Record<string, Object>;

  constructor(data: Record<string, Object>) {
    this.data = data;
  }

  static fromText(text: string): JsonReader {
    let parsed: Object;
    try {
      parsed = JSON.parse(text) as Object;
    } catch (e) {
      throw new ProtocolException('json_parse_failed');
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new ProtocolException('json_root_not_object');
    }
    return new JsonReader(parsed as Record<string, Object>);
  }

  has(key: string): boolean {
    return this.data[key] !== undefined;
  }

  private raw(key: string): Object {
    if (!this.has(key)) {
      throw new ProtocolException(`missing field: ${key}`);
    }
    return this.data[key];
  }

  string(key: string): string {
    const value = this.raw(key);
    if (typeof value !== 'string') {
      throw new ProtocolException(`field not string: ${key}`);
    }
    return value;
  }

  optionalString(key: string): string | null {
    if (!this.has(key)) {
      return null;
    }
    return this.string(key);
  }

  nullableString(key: string): string | null {
    if (!this.has(key) || this.data[key] === null) {
      return null;
    }
    return this.string(key);
  }

  number(key: string): number {
    const value = this.raw(key);
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new ProtocolException(`field not number: ${key}`);
    }
    return value;
  }

  optionalNumber(key: string): number | null {
    if (!this.has(key)) {
      return null;
    }
    return this.number(key);
  }

  nullableNumber(key: string): number | null {
    if (!this.has(key) || this.data[key] === null) {
      return null;
    }
    return this.number(key);
  }

  boolean(key: string): boolean {
    const value = this.raw(key);
    if (typeof value !== 'boolean') {
      throw new ProtocolException(`field not boolean: ${key}`);
    }
    return value;
  }

  optionalBoolean(key: string): boolean | null {
    if (!this.has(key)) {
      return null;
    }
    return this.boolean(key);
  }

  nullableBoolean(key: string): boolean | null {
    if (!this.has(key) || this.data[key] === null) {
      return null;
    }
    return this.boolean(key);
  }

  object(key: string): Record<string, Object> {
    const value = this.raw(key);
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      throw new ProtocolException(`field not object: ${key}`);
    }
    return value as Record<string, Object>;
  }

  optionalObject(key: string): Record<string, Object> | null {
    if (!this.has(key)) {
      return null;
    }
    return this.object(key);
  }

  nullableObject(key: string): Record<string, Object> | null {
    if (!this.has(key) || this.data[key] === null) {
      return null;
    }
    return this.object(key);
  }

  stringArray(key: string): string[] {
    const value = this.raw(key);
    if (!Array.isArray(value)) {
      throw new ProtocolException(`field not array: ${key}`);
    }
    const items = value as Object[];
    const result: string[] = [];
    for (const item of items) {
      if (typeof item !== 'string') {
        throw new ProtocolException(`array item not string: ${key}`);
      }
      result.push(item);
    }
    return result;
  }

  nullableStringArray(key: string): string[] | null {
    if (!this.has(key) || this.data[key] === null) {
      return null;
    }
    return this.stringArray(key);
  }

  numberArray(key: string): number[] {
    const value = this.raw(key);
    if (!Array.isArray(value)) {
      throw new ProtocolException(`field not array: ${key}`);
    }
    const items = value as Object[];
    const result: number[] = [];
    for (const item of items) {
      if (typeof item !== 'number' || !Number.isFinite(item)) {
        throw new ProtocolException(`array item not number: ${key}`);
      }
      result.push(item);
    }
    return result;
  }

  objectArray(key: string): Record<string, Object>[] {
    const value = this.raw(key);
    if (!Array.isArray(value)) {
      throw new ProtocolException(`field not array: ${key}`);
    }
    const items = value as Object[];
    const result: Record<string, Object>[] = [];
    for (const item of items) {
      if (item === null || typeof item !== 'object' || Array.isArray(item)) {
        throw new ProtocolException(`array item not object: ${key}`);
      }
      result.push(item as Record<string, Object>);
    }
    return result;
  }

  /** RFC3339 date-time：保留原始字符串（客户端不依赖时区解析）。 */
  dateTime(key: string): string {
    return this.string(key);
  }

  nullableDateTime(key: string): string | null {
    return this.nullableString(key);
  }
}

/** BootstrapStatus：{initialized: boolean, api_version: number=1}。 */
export class BootstrapStatus {
  readonly initialized: boolean;
  readonly apiVersion: number;

  constructor(initialized: boolean, apiVersion: number) {
    this.initialized = initialized;
    this.apiVersion = apiVersion;
  }

  static fromReader(reader: JsonReader): BootstrapStatus {
    const apiVersion = reader.number('api_version');
    if (apiVersion !== 1) {
      throw new ProtocolException(`unsupported api_version: ${apiVersion}`);
    }
    return new BootstrapStatus(reader.boolean('initialized'), apiVersion);
  }
}

/** TokenPair：access/refresh 令牌对。 */
export class TokenPair {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly tokenType: string;
  readonly accessExpiresAt: string;
  readonly refreshExpiresAt: string;

  constructor(accessToken: string, refreshToken: string, tokenType: string,
    accessExpiresAt: string, refreshExpiresAt: string) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    this.tokenType = tokenType;
    this.accessExpiresAt = accessExpiresAt;
    this.refreshExpiresAt = refreshExpiresAt;
  }

  static fromReader(reader: JsonReader): TokenPair {
    const tokenType = reader.string('token_type');
    if (tokenType !== 'Bearer') {
      throw new ProtocolException(`unexpected token_type: ${tokenType}`);
    }
    return new TokenPair(
      reader.string('access_token'),
      reader.string('refresh_token'),
      tokenType,
      reader.dateTime('access_expires_at'),
      reader.dateTime('refresh_expires_at'));
  }
}

/** CacheJob：事件/snapshot 共用的类型化资源（openapi CacheJob 契约）。 */
export class CacheJob {
  readonly id: string;
  readonly movieId: string;
  readonly sourceId: string;
  readonly status: string;
  readonly disposition: string | null;
  readonly remotePercent: number | null;
  readonly errorCode: string | null;
  readonly selectedMediaIds: string[];
  readonly mediaCandidates: Object[];
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly expiresAt: string | null;

  constructor(id: string, movieId: string, sourceId: string, status: string, disposition: string | null,
    remotePercent: number | null, errorCode: string | null, selectedMediaIds: string[],
    mediaCandidates: Object[], createdAt: string, updatedAt: string, expiresAt: string | null) {
    this.id = id;
    this.movieId = movieId;
    this.sourceId = sourceId;
    this.status = status;
    this.disposition = disposition;
    this.remotePercent = remotePercent;
    this.errorCode = errorCode;
    this.selectedMediaIds = selectedMediaIds;
    this.mediaCandidates = mediaCandidates;
    this.createdAt = createdAt;
    this.updatedAt = updatedAt;
    this.expiresAt = expiresAt;
  }

  static fromReader(reader: JsonReader): CacheJob {
    return new CacheJob(
      reader.string('id'),
      reader.string('movie_id'),
      reader.string('source_id'),
      reader.string('status'),
      reader.nullableString('disposition'),
      reader.nullableNumber('remote_percent'),
      reader.nullableString('error_code'),
      reader.stringArray('selected_media_ids'),
      reader.objectArray('media_candidates'),
      reader.dateTime('created_at'),
      reader.dateTime('updated_at'),
      reader.nullableDateTime('expires_at'));
  }

  /** 字段级浅合并：patch 出现的字段覆盖 base；null 权威清空。 */
  static mergePatch(base: CacheJob, patch: JsonReader): CacheJob {
    return new CacheJob(
      base.id,
      patch.has('movie_id') ? patch.string('movie_id') : base.movieId,
      patch.has('source_id') ? patch.string('source_id') : base.sourceId,
      patch.has('status') ? patch.string('status') : base.status,
      patch.has('disposition') ? patch.nullableString('disposition') : base.disposition,
      patch.has('remote_percent') ? patch.nullableNumber('remote_percent') : base.remotePercent,
      patch.has('error_code') ? patch.nullableString('error_code') : base.errorCode,
      patch.has('selected_media_ids') ? patch.stringArray('selected_media_ids') : base.selectedMediaIds,
      patch.has('media_candidates') ? patch.objectArray('media_candidates') : base.mediaCandidates,
      patch.has('created_at') ? patch.dateTime('created_at') : base.createdAt,
      patch.has('updated_at') ? patch.dateTime('updated_at') : base.updatedAt,
      patch.has('expires_at') ? patch.nullableDateTime('expires_at') : base.expiresAt);
  }
}

/** MetadataJob：snapshot 恢复最小字段。 */
export class MetadataJob {
  readonly id: string;
  readonly movieId: string | null;
  readonly number: string;
  readonly priority: number;
  readonly status: string;
  readonly attemptNo: number;
  readonly stage: string | null;
  readonly stageStatus: string | null;
  readonly errorCode: string | null;
  readonly elapsedMs: number | null;

  constructor(id: string, movieId: string | null, number: string, priority: number, status: string,
    attemptNo: number, stage: string | null, stageStatus: string | null, errorCode: string | null,
    elapsedMs: number | null) {
    this.id = id;
    this.movieId = movieId;
    this.number = number;
    this.priority = priority;
    this.status = status;
    this.attemptNo = attemptNo;
    this.stage = stage;
    this.stageStatus = stageStatus;
    this.errorCode = errorCode;
    this.elapsedMs = elapsedMs;
  }

  static fromReader(reader: JsonReader): MetadataJob {
    return new MetadataJob(
      reader.string('id'),
      reader.nullableString('movie_id'),
      reader.string('number'),
      reader.number('priority'),
      reader.string('status'),
      reader.number('attempt_no'),
      reader.nullableString('stage'),
      reader.nullableString('stage_status'),
      reader.nullableString('error_code'),
      reader.nullableNumber('elapsed_ms'));
  }
}

/** Cloud115Binding：snapshot 凭据状态。 */
export class Cloud115Binding {
  readonly bound: boolean;
  readonly status: string;
  readonly displayName: string | null;
  readonly cacheRootReady: boolean;
  readonly lastVerifiedAt: string | null;

  constructor(bound: boolean, status: string, displayName: string | null,
    cacheRootReady: boolean, lastVerifiedAt: string | null) {
    this.bound = bound;
    this.status = status;
    this.displayName = displayName;
    this.cacheRootReady = cacheRootReady;
    this.lastVerifiedAt = lastVerifiedAt;
  }

  static fromReader(reader: JsonReader): Cloud115Binding {
    const status = reader.string('status');
    const statuses: string[] = ['unbound', 'active', 'expired', 'unavailable', 'detached'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected binding status: ${status}`);
    }
    return new Cloud115Binding(reader.boolean('bound'), status,
      reader.nullableString('display_name'), reader.boolean('cache_root_ready'),
      reader.nullableDateTime('last_verified_at'));
  }
}

/** Notification：未读/已读通知。 */
export class Notification {
  readonly id: string;
  readonly type: string;
  readonly resourceId: string | null;
  readonly createdAt: string;
  readonly readAt: string | null;

  constructor(id: string, type: string, resourceId: string | null, createdAt: string, readAt: string | null) {
    this.id = id;
    this.type = type;
    this.resourceId = resourceId;
    this.createdAt = createdAt;
    this.readAt = readAt;
  }

  static fromReader(reader: JsonReader): Notification {
    return new Notification(
      reader.string('id'),
      reader.string('type'),
      reader.nullableString('resource_id'),
      reader.dateTime('created_at'),
      reader.nullableDateTime('read_at'));
  }

  /** 浅合并：read_at 更新（null 权威清空）。 */
  static mergePatch(base: Notification, patch: JsonReader): Notification {
    return new Notification(
      base.id,
      patch.has('type') ? patch.string('type') : base.type,
      patch.has('resource_id') ? patch.nullableString('resource_id') : base.resourceId,
      patch.has('created_at') ? patch.dateTime('created_at') : base.createdAt,
      patch.has('read_at') ? patch.nullableDateTime('read_at') : base.readAt);
  }
}

/** QueueDiagnostic：snapshot 队列计数（openapi 扁平 6 字段）。 */
export class QueueDiagnostic {
  readonly metadataQueued: number;
  readonly metadataRunning: number;
  readonly metadataPaused: boolean;
  readonly cacheQueued: number;
  readonly cacheRunning: number;
  readonly cacheReady: number;

  constructor(metadataQueued: number, metadataRunning: number, metadataPaused: boolean,
    cacheQueued: number, cacheRunning: number, cacheReady: number) {
    this.metadataQueued = metadataQueued;
    this.metadataRunning = metadataRunning;
    this.metadataPaused = metadataPaused;
    this.cacheQueued = cacheQueued;
    this.cacheRunning = cacheRunning;
    this.cacheReady = cacheReady;
  }

  static fromReader(reader: JsonReader): QueueDiagnostic {
    const metadataRunning = reader.number('metadata_running');
    const cacheQueued = reader.number('cache_queued');
    const cacheRunning = reader.number('cache_running');
    if (metadataRunning < 0 || metadataRunning > 3) {
      throw new ProtocolException('QueueDiagnostic.metadata_running out of range');
    }
    if (cacheQueued < 0 || cacheQueued > 10) {
      throw new ProtocolException('QueueDiagnostic.cache_queued out of range');
    }
    if (cacheRunning < 0 || cacheRunning > 2) {
      throw new ProtocolException('QueueDiagnostic.cache_running out of range');
    }
    return new QueueDiagnostic(
      reader.number('metadata_queued'),
      metadataRunning,
      reader.boolean('metadata_paused'),
      cacheQueued,
      cacheRunning,
      reader.number('cache_ready'));
  }
}

/** PlaybackProgress：影片级播放进度（AC-068；TASK-111 前为 null）。 */
export class PlaybackProgress {
  readonly positionSeconds: number;
  readonly durationSeconds: number | null;
  readonly completed: boolean;
  readonly version: number;

  constructor(positionSeconds: number, durationSeconds: number | null, completed: boolean, version: number) {
    this.positionSeconds = positionSeconds;
    this.durationSeconds = durationSeconds;
    this.completed = completed;
    this.version = version;
  }

  static fromReader(reader: JsonReader): PlaybackProgress {
    return new PlaybackProgress(
      reader.number('position_seconds'),
      reader.nullableNumber('duration_seconds'),
      reader.boolean('completed'),
      reader.number('version'));
  }

  /** 进度比例：completed 或未知时长返回 null（按钮显示“播放/已看完”）。 */
  fraction(): number | null {
    if (this.completed || this.durationSeconds === null || this.durationSeconds <= 0) {
      return null;
    }
    const ratio = this.positionSeconds / this.durationSeconds;
    return ratio < 0 ? 0 : (ratio > 1 ? 1 : ratio);
  }
}

/** MovieSummary：搜索影片结果（openapi MovieSummary）。 */
export class MovieSummary {
  readonly id: string;
  readonly number: string;
  readonly title: string;
  readonly titleOriginal: string | null;
  readonly coverUrl: string | null;
  readonly publishDate: string | null;
  readonly labels: string[];
  readonly favorite: boolean;
  readonly sourceCount: number;
  readonly progress: PlaybackProgress | null;

  constructor(id: string, number: string, title: string, titleOriginal: string | null,
    coverUrl: string | null, publishDate: string | null, labels: string[],
    favorite: boolean, sourceCount: number, progress: PlaybackProgress | null) {
    this.id = id;
    this.number = number;
    this.title = title;
    this.titleOriginal = titleOriginal;
    this.coverUrl = coverUrl;
    this.publishDate = publishDate;
    this.labels = labels;
    this.favorite = favorite;
    this.sourceCount = sourceCount;
    this.progress = progress;
  }

  static fromReader(reader: JsonReader): MovieSummary {
    let progress: PlaybackProgress | null = null;
    if (reader.has('progress') && reader.nullableObject('progress') !== null) {
      try {
        progress = PlaybackProgress.fromReader(new JsonReader(reader.object('progress')));
      } catch (err) {
        // 进度子对象异常不拖垮整页列表（降级为无进度）
        progress = null;
      }
    }
    return new MovieSummary(
      reader.string('id'),
      reader.string('number'),
      reader.string('title'),
      reader.nullableString('title_original'),
      reader.nullableString('cover_url'),
      reader.nullableString('publish_date'),
      reader.stringArray('labels'),
      reader.boolean('favorite'),
      reader.number('source_count'),
      progress);
  }
}

/** MoviePage：游标分页的影片列表（items + next_cursor）。 */
export class MoviePage {
  readonly items: MovieSummary[];
  readonly nextCursor: string | null;

  constructor(items: MovieSummary[], nextCursor: string | null) {
    this.items = items;
    this.nextCursor = nextCursor;
  }

  static fromText(text: string): MoviePage {
    const reader = JsonReader.fromText(text);
    const items: MovieSummary[] = [];
    for (const item of reader.objectArray('items')) {
      items.push(MovieSummary.fromReader(new JsonReader(item)));
    }
    return new MoviePage(items, reader.nullableString('next_cursor'));
  }
}

/** MovieSource：影片多来源资源（openapi MovieSource；rejected 不可选且不输出 source_id）。 */
export class MovieSource {
  readonly id: string;
  readonly website: string;
  readonly externalPostId: number;
  readonly title: string;
  readonly publishDate: string | null;
  readonly category: string;
  readonly labels: string[];
  readonly resourceSizeMb: number | null;
  readonly videoFileSizeBytes: number | null;
  readonly availability: string;

  constructor(id: string, website: string, externalPostId: number, title: string,
    publishDate: string | null, category: string, labels: string[],
    resourceSizeMb: number | null, videoFileSizeBytes: number | null, availability: string) {
    this.id = id;
    this.website = website;
    this.externalPostId = externalPostId;
    this.title = title;
    this.publishDate = publishDate;
    this.category = category;
    this.labels = labels;
    this.resourceSizeMb = resourceSizeMb;
    this.videoFileSizeBytes = videoFileSizeBytes;
    this.availability = availability;
  }

  /** rejected 永久禁用（不得输出 source_id）。 */
  isSelectable(): boolean {
    return this.availability !== 'rejected';
  }

  static fromReader(reader: JsonReader): MovieSource {
    const id = reader.string('id');
    if (!SOURCE_UUID_PATTERN.test(id)) {
      throw new ProtocolException('MovieSource.id is not a uuid');
    }
    const website = reader.string('website');
    if (website !== 'sehuatang' && website !== 'x1080x') {
      throw new ProtocolException(`unexpected source website: ${website}`);
    }
    const externalPostId = reader.number('external_post_id');
    if (externalPostId < 1 || Math.floor(externalPostId) !== externalPostId) {
      throw new ProtocolException('MovieSource.external_post_id must be a positive integer');
    }
    const title = reader.string('title');
    if (title.length === 0) {
      throw new ProtocolException('MovieSource.title is empty');
    }
    const category = reader.string('category');
    const categories: string[] = ['亚洲有码', '亚洲无码', '中文字幕', '4K原版', '素人有码', 'FC2'];
    if (!categories.includes(category)) {
      throw new ProtocolException(`unexpected source category: ${category}`);
    }
    const labels = reader.stringArray('labels');
    if (labels.length > 4 || !uniqueNonEmpty(labels)) {
      throw new ProtocolException('MovieSource.labels is invalid');
    }
    const knownLabels: string[] = ['subtitle', 'cracked', '4k', 'censored'];
    for (const label of labels) {
      if (!knownLabels.includes(label)) {
        throw new ProtocolException(`unexpected source label: ${label}`);
      }
    }
    const sizeMb = reader.nullableNumber('resource_size_mb');
    if (sizeMb !== null && sizeMb < 0) {
      throw new ProtocolException('MovieSource.resource_size_mb must be non-negative');
    }
    const sizeBytes = reader.nullableNumber('video_file_size_bytes');
    if (sizeBytes !== null && sizeBytes < 0) {
      throw new ProtocolException('MovieSource.video_file_size_bytes must be non-negative');
    }
    const availability = reader.string('availability');
    const states: string[] = ['available', 'queued', 'running', 'ready', 'failed', 'rejected'];
    if (!states.includes(availability)) {
      throw new ProtocolException(`unexpected source availability: ${availability}`);
    }
    return new MovieSource(id, website, externalPostId, title,
      reader.nullableString('publish_date'), category, labels, sizeMb, sizeBytes, availability);
  }
}

/** MovieDetail：/movies/{id} 聚合详情（openapi MovieDetail；metadata_state 非 core_ready 为受限详情）。 */
export class MovieDetail {
  readonly id: string;
  readonly number: string;
  readonly title: string;
  readonly titleOriginal: string | null;
  readonly coverUrl: string | null;
  readonly publishDate: string | null;
  readonly labels: string[];
  readonly favorite: boolean;
  readonly sourceCount: number;
  readonly progress: PlaybackProgress | null;
  readonly metadataState: string;
  readonly metadataErrorCode: string | null;
  readonly releaseDate: string | null;
  readonly maker: string | null;
  readonly series: string | null;
  readonly director: string | null;
  readonly score: number | null;
  readonly description: string | null;
  readonly descriptionOriginal: string | null;
  readonly actors: ActorSummary[];
  readonly tags: string[];
  readonly plotImageUrls: string[];
  readonly sources: MovieSource[];

  constructor(id: string, number: string, title: string, titleOriginal: string | null,
    coverUrl: string | null, publishDate: string | null, labels: string[],
    favorite: boolean, sourceCount: number, progress: PlaybackProgress | null,
    metadataState: string, metadataErrorCode: string | null, releaseDate: string | null,
    maker: string | null, series: string | null, director: string | null,
    score: number | null, description: string | null, descriptionOriginal: string | null,
    actors: ActorSummary[], tags: string[], plotImageUrls: string[],
    sources: MovieSource[]) {
    this.id = id;
    this.number = number;
    this.title = title;
    this.titleOriginal = titleOriginal;
    this.coverUrl = coverUrl;
    this.publishDate = publishDate;
    this.labels = labels;
    this.favorite = favorite;
    this.sourceCount = sourceCount;
    this.progress = progress;
    this.metadataState = metadataState;
    this.metadataErrorCode = metadataErrorCode;
    this.releaseDate = releaseDate;
    this.maker = maker;
    this.series = series;
    this.director = director;
    this.score = score;
    this.description = description;
    this.descriptionOriginal = descriptionOriginal;
    this.actors = actors;
    this.tags = tags;
    this.plotImageUrls = plotImageUrls;
    this.sources = sources;
  }

  /** 受限详情：不显示收藏按钮、不调用 favorite API；来源选择仍可用。 */
  isLimited(): boolean {
    return this.metadataState !== 'core_ready';
  }

  /** 收藏成功后替换 favorite（保持其他字段不变）。 */
  withFavorite(enabled: boolean): MovieDetail {
    return new MovieDetail(this.id, this.number, this.title, this.titleOriginal, this.coverUrl,
      this.publishDate, this.labels, enabled, this.sourceCount, this.progress,
      this.metadataState, this.metadataErrorCode, this.releaseDate, this.maker, this.series,
      this.director, this.score, this.description, this.descriptionOriginal,
      this.actors, this.tags, this.plotImageUrls, this.sources);
  }

  private static requireSourceCount(reader: JsonReader): number {
    const count = reader.number('source_count');
    if (count < 1 || Math.floor(count) !== count) {
      throw new ProtocolException('MovieDetail.source_count must be a positive integer');
    }
    return count;
  }

  static fromText(text: string): MovieDetail {
    const reader = JsonReader.fromText(text);
    const id = reader.string('id');
    const labels = reader.stringArray('labels');
    if (labels.length > 4 || !uniqueNonEmpty(labels)) {
      throw new ProtocolException('MovieDetail.labels is invalid');
    }
    const knownLabels: string[] = ['subtitle', 'cracked', '4k', 'censored'];
    for (const label of labels) {
      if (!knownLabels.includes(label)) {
        throw new ProtocolException(`unexpected movie label: ${label}`);
      }
    }
    const metadataState = reader.string('metadata_state');
    const states: string[] = ['core_ready', 'queued', 'running', 'failed'];
    if (!states.includes(metadataState)) {
      throw new ProtocolException(`unexpected metadata_state: ${metadataState}`);
    }
    const metadataErrorCode = reader.nullableString('metadata_error_code');
    if (metadataErrorCode !== null && metadataState !== 'failed') {
      throw new ProtocolException('metadata_error_code is only allowed for failed metadata');
    }
    const actors: ActorSummary[] = [];
    const actorIds: string[] = [];
    for (const item of reader.objectArray('actors')) {
      if (actors.length >= 100) {
        throw new ProtocolException('MovieDetail.actors exceeds limit');
      }
      const actor = ActorSummary.fromReader(new JsonReader(item));
      if (actorIds.includes(actor.id)) {
        throw new ProtocolException('MovieDetail.actors has duplicate ids');
      }
      actorIds.push(actor.id);
      actors.push(actor);
    }
    const tags = reader.stringArray('tags');
    if (tags.length > 100 || !uniqueNonEmpty(tags)) {
      throw new ProtocolException('MovieDetail.tags is invalid');
    }
    const plotImageUrls = reader.stringArray('plot_image_urls');
    if (plotImageUrls.length > 100 || !uniqueNonEmpty(plotImageUrls)) {
      throw new ProtocolException('MovieDetail.plot_image_urls is invalid');
    }
    const sources: MovieSource[] = [];
    const sourceIds: string[] = [];
    for (const item of reader.objectArray('sources')) {
      if (sources.length >= 100) {
        throw new ProtocolException('MovieDetail.sources exceeds limit');
      }
      const source = MovieSource.fromReader(new JsonReader(item));
      if (sourceIds.includes(source.id)) {
        throw new ProtocolException('MovieDetail.sources has duplicate ids');
      }
      sourceIds.push(source.id);
      sources.push(source);
    }
    let progress: PlaybackProgress | null = null;
    if (reader.has('progress') && reader.nullableObject('progress') !== null) {
      try {
        progress = PlaybackProgress.fromReader(new JsonReader(reader.object('progress')));
      } catch (err) {
        // 进度子对象异常不拖垮详情（降级为无进度）
        progress = null;
      }
    }
    return new MovieDetail(id, reader.string('number'), reader.string('title'),
      reader.nullableString('title_original'), reader.nullableString('cover_url'),
      reader.nullableString('publish_date'), labels,
      reader.boolean('favorite'), MovieDetail.requireSourceCount(reader), progress,
      metadataState, metadataErrorCode, reader.nullableString('release_date'),
      reader.nullableString('maker'), reader.nullableString('series'),
      reader.nullableString('director'), reader.nullableNumber('score'),
      reader.nullableString('description'), reader.nullableString('description_original'),
      actors, tags, plotImageUrls, sources);
  }

}

/** 严格 UUID 8-4-4-4-12（MovieSource/MovieDetail.id）。 */
const SOURCE_UUID_PATTERN: RegExp =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/** 字符串数组非空且不重复（集合约束辅助）。 */
function uniqueNonEmpty(values: string[]): boolean {
  const seen: string[] = [];
  for (const value of values) {
    if (value.length === 0 || seen.includes(value)) {
      return false;
    }
    seen.push(value);
  }
  return true;
}

/** RankingItem：榜单条目（rank 正整数允许间隙；movie 复用 MovieSummary）。 */
export class RankingItem {
  readonly rank: number;
  readonly movie: MovieSummary;

  constructor(rank: number, movie: MovieSummary) {
    this.rank = rank;
    this.movie = movie;
  }

  static fromReader(reader: JsonReader): RankingItem {
    const rank = reader.number('rank');
    if (!Number.isInteger(rank) || rank < 1) {
      throw new ProtocolException('RankingItem.rank is invalid');
    }
    return new RankingItem(rank, MovieSummary.fromReader(new JsonReader(reader.object('movie'))));
  }
}

/** RankingPage：/rankings 响应（openapi RankingPage）。 */
export class RankingPage {
  static readonly BOARDS: string[] = ['daily', 'weekly', 'monthly', 'top250'];

  readonly board: string;
  readonly year: number | null;
  readonly availableYears: number[];
  readonly syncedAt: string;
  readonly items: RankingItem[];
  readonly nextCursor: string | null;

  constructor(board: string, year: number | null, availableYears: number[],
    syncedAt: string, items: RankingItem[], nextCursor: string | null) {
    this.board = board;
    this.year = year;
    this.availableYears = availableYears;
    this.syncedAt = syncedAt;
    this.items = items;
    this.nextCursor = nextCursor;
  }

  static fromText(text: string): RankingPage {
    const reader = JsonReader.fromText(text);
    const board = reader.string('board');
    if (!RankingPage.BOARDS.includes(board)) {
      throw new ProtocolException(`RankingPage.board is invalid: ${board}`);
    }
    const year = reader.nullableNumber('year');
    if (year !== null &&
      (board !== 'top250' || !Number.isInteger(year) || year < 2008 || year > 2200)) {
      throw new ProtocolException('RankingPage.year is invalid');
    }
    const availableYears = reader.numberArray('available_years');
    RankingPage.validateAvailableYears(availableYears, board);
    const items: RankingItem[] = [];
    for (const item of reader.objectArray('items')) {
      if (items.length >= 100) {
        throw new ProtocolException('RankingPage.items exceeds limit');
      }
      items.push(RankingItem.fromReader(new JsonReader(item)));
    }
    return new RankingPage(board, year, availableYears,
      reader.dateTime('synced_at'), items, reader.nullableString('next_cursor'));
  }

  private static validateAvailableYears(years: number[], board: string): void {
    if (years.length > 100) {
      throw new ProtocolException('RankingPage.available_years exceeds limit');
    }
    if (board !== 'top250') {
      if (years.length > 0) {
        throw new ProtocolException('RankingPage.available_years invalid for board');
      }
      return;
    }
    let previous: number | null = null;
    for (const year of years) {
      if (!Number.isInteger(year) || year < 2008 || year > 2200) {
        throw new ProtocolException('RankingPage.available_years contains invalid year');
      }
      if (previous !== null && year >= previous) {
        throw new ProtocolException('RankingPage.available_years must be descending');
      }
      previous = year;
    }
  }
}

/** ActorSummary：搜索女优结果（openapi ActorSummary）。 */
export class ActorSummary {
  readonly id: string;
  readonly displayName: string;
  readonly nameJa: string | null;
  readonly nameZh: string | null;
  readonly aliases: string[];
  readonly profileUrl: string | null;
  readonly favorite: boolean;

  constructor(id: string, displayName: string, nameJa: string | null, nameZh: string | null,
    aliases: string[], profileUrl: string | null, favorite: boolean) {
    this.id = id;
    this.displayName = displayName;
    this.nameJa = nameJa;
    this.nameZh = nameZh;
    this.aliases = aliases;
    this.profileUrl = profileUrl;
    this.favorite = favorite;
  }

  static fromReader(reader: JsonReader): ActorSummary {
    return new ActorSummary(
      reader.string('id'),
      reader.string('display_name'),
      reader.nullableString('name_ja'),
      reader.nullableString('name_zh'),
      reader.stringArray('aliases'),
      reader.nullableString('profile_url'),
      reader.boolean('favorite'));
  }
}

/** ActorDetail：/actors/{id} 响应（openapi ActorDetail）。 */
export class ActorDetail {
  readonly summary: ActorSummary;
  readonly bio: string | null;
  readonly bioOriginal: string | null;
  readonly galleryUrls: string[];
  readonly movies: MovieSummary[];

  constructor(summary: ActorSummary, bio: string | null, bioOriginal: string | null,
    galleryUrls: string[], movies: MovieSummary[]) {
    this.summary = summary;
    this.bio = bio;
    this.bioOriginal = bioOriginal;
    this.galleryUrls = galleryUrls;
    this.movies = movies;
  }

  static fromText(text: string): ActorDetail {
    const reader = JsonReader.fromText(text);
    const summary = ActorSummary.fromReader(reader);
    const galleryUrls = reader.stringArray('gallery_urls');
    if (galleryUrls.length > 100 || !uniqueNonEmpty(galleryUrls)) {
      throw new ProtocolException('ActorDetail.gallery_urls is invalid');
    }
    const movies: MovieSummary[] = [];
    for (const item of reader.objectArray('movies')) {
      if (movies.length >= 100) {
        throw new ProtocolException('ActorDetail.movies exceeds limit');
      }
      movies.push(MovieSummary.fromReader(new JsonReader(item)));
    }
    return new ActorDetail(summary, reader.nullableString('bio'),
      reader.nullableString('bio_original'), galleryUrls, movies);
  }
}

/** ActorPage：/actors 游标分页列表（items + next_cursor）。 */
export class ActorPage {
  readonly items: ActorSummary[];
  readonly nextCursor: string | null;

  constructor(items: ActorSummary[], nextCursor: string | null) {
    this.items = items;
    this.nextCursor = nextCursor;
  }

  static fromText(text: string): ActorPage {
    const reader = JsonReader.fromText(text);
    const items: ActorSummary[] = [];
    for (const item of reader.objectArray('items')) {
      if (items.length >= 100) {
        throw new ProtocolException('ActorPage.items exceeds limit');
      }
      items.push(ActorSummary.fromReader(new JsonReader(item)));
    }
    return new ActorPage(items, reader.nullableString('next_cursor'));
  }
}

/** PendingMetadata：搜索补全状态（queued/running/failed）。 */
export class PendingMetadata {
  readonly movieId: string;
  readonly number: string;
  readonly state: string;
  readonly metadataJobId: string;

  constructor(movieId: string, number: string, state: string, metadataJobId: string) {
    this.movieId = movieId;
    this.number = number;
    this.state = state;
    this.metadataJobId = metadataJobId;
  }

  static fromReader(reader: JsonReader): PendingMetadata {
    const state = reader.string('state');
    if (state !== 'queued' && state !== 'running' && state !== 'failed') {
      throw new ProtocolException(`unexpected pending state: ${state}`);
    }
    return new PendingMetadata(
      reader.string('movie_id'),
      reader.string('number'),
      state,
      reader.string('metadata_job_id'));
  }
}

/** SearchResult：全局搜索结果（movies/actors/pending_metadata 三分组）。 */
export class SearchResult {
  readonly movies: MovieSummary[];
  readonly actors: ActorSummary[];
  readonly pendingMetadata: PendingMetadata[];

  constructor(movies: MovieSummary[], actors: ActorSummary[], pendingMetadata: PendingMetadata[]) {
    this.movies = movies;
    this.actors = actors;
    this.pendingMetadata = pendingMetadata;
  }

  static fromText(text: string): SearchResult {
    const reader = JsonReader.fromText(text);
    const movies: MovieSummary[] = [];
    for (const item of reader.objectArray('movies')) {
      movies.push(MovieSummary.fromReader(new JsonReader(item)));
    }
    const actors: ActorSummary[] = [];
    for (const item of reader.objectArray('actors')) {
      actors.push(ActorSummary.fromReader(new JsonReader(item)));
    }
    const pending: PendingMetadata[] = [];
    for (const item of reader.objectArray('pending_metadata')) {
      pending.push(PendingMetadata.fromReader(new JsonReader(item)));
    }
    return new SearchResult(movies, actors, pending);
  }
}

/** EventSnapshot：REST 恢复快照。 */
export class EventSnapshot {
  readonly snapshotVersion: number;
  readonly lastEventId: string | null;
  readonly queues: QueueDiagnostic;
  readonly cacheJobs: CacheJob[];
  readonly metadataJobs: MetadataJob[];
  readonly cloud115Binding: Cloud115Binding;
  readonly notifications: Notification[];

  constructor(snapshotVersion: number, lastEventId: string | null, queues: QueueDiagnostic,
    cacheJobs: CacheJob[], metadataJobs: MetadataJob[], cloud115Binding: Cloud115Binding,
    notifications: Notification[]) {
    this.snapshotVersion = snapshotVersion;
    this.lastEventId = lastEventId;
    this.queues = queues;
    this.cacheJobs = cacheJobs;
    this.metadataJobs = metadataJobs;
    this.cloud115Binding = cloud115Binding;
    this.notifications = notifications;
  }

  static fromText(text: string): EventSnapshot {
    const reader = JsonReader.fromText(text);
    const snapshotVersion = reader.number('snapshot_version');
    const lastEventId = reader.nullableString('last_event_id');
    const queues = QueueDiagnostic.fromReader(new JsonReader(reader.object('queues')));
    const cacheJobs: CacheJob[] = [];
    for (const item of reader.objectArray('cache_jobs')) {
      cacheJobs.push(CacheJob.fromReader(new JsonReader(item)));
    }
    const metadataJobs: MetadataJob[] = [];
    for (const item of reader.objectArray('metadata_jobs')) {
      metadataJobs.push(MetadataJob.fromReader(new JsonReader(item)));
    }
    const notifications: Notification[] = [];
    for (const item of reader.objectArray('notifications')) {
      notifications.push(Notification.fromReader(new JsonReader(item)));
    }
    return new EventSnapshot(snapshotVersion, lastEventId, queues, cacheJobs, metadataJobs,
      Cloud115Binding.fromReader(new JsonReader(reader.object('cloud115_binding'))), notifications);
  }
}

/** QrSession：115 扫码会话（openapi QrSession；PNG 只存内存）。 */
export class QrSession {
  readonly id: string;
  readonly status: string;
  readonly qrcodePngBase64: string | null;
  readonly expiresAt: string;

  constructor(id: string, status: string, qrcodePngBase64: string | null, expiresAt: string) {
    this.id = id;
    this.status = status;
    this.qrcodePngBase64 = qrcodePngBase64;
    this.expiresAt = expiresAt;
  }

  static fromText(text: string): QrSession {
    const reader = JsonReader.fromText(text);
    const id = reader.string('id');
    if (!SOURCE_UUID_PATTERN.test(id)) {
      throw new ProtocolException('QrSession.id is not a uuid');
    }
    const status = reader.string('status');
    const statuses: string[] = ['waiting', 'scanned', 'confirmed', 'expired', 'canceled'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected qr status: ${status}`);
    }
    const png = reader.nullableString('qrcode_png_base64');
    if (png !== null && !png.startsWith('iVBOR')) {
      // PNG base64 必须以合法 PNG 魔数开头（iVBORw0KGgo）
      throw new ProtocolException('QrSession.qrcode_png_base64 is not a png');
    }
    return new QrSession(id, status, png, reader.dateTime('expires_at'));
  }
}

/** CacheCapacity：固定容量计数（running2/queued10/ready20）。 */
export class CacheCapacity {
  readonly running: number;
  readonly runningLimit: number;
  readonly queued: number;
  readonly queuedLimit: number;
  readonly ready: number;
  readonly readyLimit: number;

  constructor(running: number, runningLimit: number, queued: number, queuedLimit: number,
    ready: number, readyLimit: number) {
    this.running = running;
    this.runningLimit = runningLimit;
    this.queued = queued;
    this.queuedLimit = queuedLimit;
    this.ready = ready;
    this.readyLimit = readyLimit;
  }

  static fromReader(reader: JsonReader): CacheCapacity {
    const running = reader.number('running');
    const queued = reader.number('queued');
    const ready = reader.number('ready');
    const runningLimit = reader.number('running_limit');
    const queuedLimit = reader.number('queued_limit');
    const readyLimit = reader.number('ready_limit');
    if (runningLimit !== 2 || queuedLimit !== 10 || readyLimit !== 20) {
      throw new ProtocolException('CacheCapacity limits are not 2/10/20');
    }
    if (running > runningLimit || queued > queuedLimit || ready > readyLimit) {
      throw new ProtocolException('CacheCapacity count exceeds limit');
    }
    return new CacheCapacity(running, runningLimit, queued, queuedLimit, ready, readyLimit);
  }
}

/** CacheJobDetail：/cache-jobs 列表/详情任务（13 状态）。 */
export class CacheJobDetail {
  readonly id: string;
  readonly movieId: string;
  readonly sourceId: string;
  readonly status: string;
  readonly remotePercent: number | null;
  readonly errorCode: string | null;
  readonly mediaCandidates: Object[];
  readonly selectedMediaIds: string[];
  readonly subtitles: Object[];
  readonly readyAt: string | null;
  readonly expiresAt: string | null;
  readonly createdAt: string;
  readonly updatedAt: string;

  constructor(id: string, movieId: string, sourceId: string, status: string,
    remotePercent: number | null, errorCode: string | null, mediaCandidates: Object[],
    selectedMediaIds: string[], subtitles: Object[], readyAt: string | null,
    expiresAt: string | null, createdAt: string, updatedAt: string) {
    this.id = id;
    this.movieId = movieId;
    this.sourceId = sourceId;
    this.status = status;
    this.remotePercent = remotePercent;
    this.errorCode = errorCode;
    this.mediaCandidates = mediaCandidates;
    this.selectedMediaIds = selectedMediaIds;
    this.subtitles = subtitles;
    this.readyAt = readyAt;
    this.expiresAt = expiresAt;
    this.createdAt = createdAt;
    this.updatedAt = updatedAt;
  }

  static fromText(text: string): CacheJobDetail {
    return CacheJobDetail.fromReader(JsonReader.fromText(text));
  }

  static fromReader(reader: JsonReader): CacheJobDetail {
    const id = reader.string('id');
    if (!SOURCE_UUID_PATTERN.test(id)) {
      throw new ProtocolException('CacheJobDetail.id is not a uuid');
    }
    const status = reader.string('status');
    const statuses: string[] = ['queued', 'submitting', 'offlining', 'submit_uncertain',
      'resolving', 'awaiting_selection', 'ready', 'cancelling', 'cleaning', 'cleanup_failed',
      'failed', 'cleaned', 'detached'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected cache job status: ${status}`);
    }
    const remotePercent = reader.nullableNumber('remote_percent');
    if (remotePercent !== null && (remotePercent < 0 || remotePercent > 100)) {
      throw new ProtocolException('CacheJobDetail.remote_percent out of range');
    }
    return new CacheJobDetail(id, reader.string('movie_id'), reader.string('source_id'),
      status, remotePercent, reader.nullableString('error_code'),
      reader.objectArray('media_candidates'), reader.stringArray('selected_media_ids'),
      reader.objectArray('subtitles'), reader.nullableDateTime('ready_at'),
      reader.nullableDateTime('expires_at'), reader.dateTime('created_at'),
      reader.dateTime('updated_at'));
  }
}

/** CacheJobPage：分页任务列表 + 容量。 */
export class CacheJobPage {
  readonly items: CacheJobDetail[];
  readonly capacity: CacheCapacity;
  readonly nextCursor: string | null;

  constructor(items: CacheJobDetail[], capacity: CacheCapacity, nextCursor: string | null) {
    this.items = items;
    this.capacity = capacity;
    this.nextCursor = nextCursor;
  }

  static fromText(text: string): CacheJobPage {
    const reader = JsonReader.fromText(text);
    const items: CacheJobDetail[] = [];
    const ids: string[] = [];
    for (const item of reader.objectArray('items')) {
      if (items.length >= 100) {
        throw new ProtocolException('CacheJobPage.items exceeds limit');
      }
      const job = CacheJobDetail.fromReader(new JsonReader(item));
      if (ids.includes(job.id)) {
        throw new ProtocolException('CacheJobPage.items has duplicate ids');
      }
      ids.push(job.id);
      items.push(job);
    }
    return new CacheJobPage(items, CacheCapacity.fromReader(new JsonReader(reader.object('capacity'))),
      reader.nullableString('next_cursor'));
  }
}

/** ProviderState：数据源配置与连通状态。 */
export class ProviderState {
  readonly configured: boolean;
  readonly status: string;
  readonly lastCheckedAt: string | null;
  readonly lastErrorCode: string | null;

  constructor(configured: boolean, status: string, lastCheckedAt: string | null,
    lastErrorCode: string | null) {
    this.configured = configured;
    this.status = status;
    this.lastCheckedAt = lastCheckedAt;
    this.lastErrorCode = lastErrorCode;
  }

  static fromReader(reader: JsonReader): ProviderState {
    const status = reader.string('status');
    const statuses: string[] = ['unknown', 'available', 'unavailable', 'credentials_invalid',
      'not_configured'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected provider status: ${status}`);
    }
    return new ProviderState(reader.boolean('configured'), status,
      reader.nullableDateTime('last_checked_at'), reader.nullableString('last_error_code'));
  }
}

/** JavdbSettings：对象级 CAS 数据源配置（密码只回显 configured）。 */
export class JavdbSettings {
  readonly configured: boolean;
  readonly status: string;
  readonly lastCheckedAt: string | null;
  readonly lastErrorCode: string | null;
  readonly username: string | null;
  readonly passwordConfigured: boolean;
  readonly version: number;

  constructor(configured: boolean, status: string, lastCheckedAt: string | null,
    lastErrorCode: string | null, username: string | null, passwordConfigured: boolean,
    version: number) {
    this.configured = configured;
    this.status = status;
    this.lastCheckedAt = lastCheckedAt;
    this.lastErrorCode = lastErrorCode;
    this.username = username;
    this.passwordConfigured = passwordConfigured;
    this.version = version;
  }

  static fromReader(reader: JsonReader): JavdbSettings {
    const base = ProviderState.fromReader(reader);
    return new JavdbSettings(base.configured, base.status, base.lastCheckedAt, base.lastErrorCode,
      reader.nullableString('username'), reader.boolean('password_configured'),
      reader.number('version'));
  }
}

/** AiSettings：对象级 CAS AI 配置（API key 只回显 configured）。 */
export class AiSettings {
  readonly configured: boolean;
  readonly status: string;
  readonly lastCheckedAt: string | null;
  readonly lastErrorCode: string | null;
  readonly baseUrl: string | null;
  readonly model: string | null;
  readonly timeoutSeconds: number | null;
  readonly apiKeyConfigured: boolean;
  readonly version: number;

  constructor(configured: boolean, status: string, lastCheckedAt: string | null,
    lastErrorCode: string | null, baseUrl: string | null, model: string | null,
    timeoutSeconds: number | null, apiKeyConfigured: boolean, version: number) {
    this.configured = configured;
    this.status = status;
    this.lastCheckedAt = lastCheckedAt;
    this.lastErrorCode = lastErrorCode;
    this.baseUrl = baseUrl;
    this.model = model;
    this.timeoutSeconds = timeoutSeconds;
    this.apiKeyConfigured = apiKeyConfigured;
    this.version = version;
  }

  static fromReader(reader: JsonReader): AiSettings {
    const base = ProviderState.fromReader(reader);
    const timeout = reader.nullableNumber('timeout_seconds');
    if (timeout !== null && (timeout < 1 || timeout > 600)) {
      throw new ProtocolException('AiSettings.timeout_seconds out of range');
    }
    return new AiSettings(base.configured, base.status, base.lastCheckedAt, base.lastErrorCode,
      reader.nullableString('base_url'), reader.nullableString('model'), timeout,
      reader.boolean('api_key_configured'), reader.number('version'));
  }
}

/** MgdbSettings：MGDB 数据源（source_url 仅 GitHub HTTPS 仓库）。 */
export class MgdbSettings {
  readonly configured: boolean;
  readonly sourceUrl: string | null;
  readonly version: number;

  constructor(configured: boolean, sourceUrl: string | null, version: number) {
    this.configured = configured;
    this.sourceUrl = sourceUrl;
    this.version = version;
  }

  static fromReader(reader: JsonReader): MgdbSettings {
    return new MgdbSettings(reader.boolean('configured'),
      reader.nullableString('source_url'), reader.number('version'));
  }
}

/** SyncRunState：30D 增量/全量同步状态。 */
export class SyncRunState {
  readonly status: string;
  readonly importedCount: number;
  readonly releaseId: string | null;
  readonly lastSuccessfulAt: string | null;
  readonly nextScheduledAt: string | null;

  constructor(status: string, importedCount: number, releaseId: string | null,
    lastSuccessfulAt: string | null, nextScheduledAt: string | null) {
    this.status = status;
    this.importedCount = importedCount;
    this.releaseId = releaseId;
    this.lastSuccessfulAt = lastSuccessfulAt;
    this.nextScheduledAt = nextScheduledAt;
  }

  static fromReader(reader: JsonReader): SyncRunState {
    const status = reader.string('status');
    const statuses: string[] = ['never', 'running', 'succeeded', 'failed'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected sync state: ${status}`);
    }
    return new SyncRunState(status, reader.number('imported_count'),
      reader.nullableString('release_id'), reader.nullableDateTime('last_successful_at'),
      reader.nullableDateTime('next_scheduled_at'));
  }
}

/** AvdbSyncStatus：AVdb 同步状态（增量 + 全量）。 */
export class AvdbSyncStatus {
  readonly incremental30d: SyncRunState;
  readonly fullReconcile: SyncRunState;

  constructor(incremental30d: SyncRunState, fullReconcile: SyncRunState) {
    this.incremental30d = incremental30d;
    this.fullReconcile = fullReconcile;
  }

  static fromReader(reader: JsonReader): AvdbSyncStatus {
    return new AvdbSyncStatus(
      SyncRunState.fromReader(new JsonReader(reader.object('incremental_30d'))),
      SyncRunState.fromReader(new JsonReader(reader.object('full_reconcile'))));
  }
}

/** Settings：115/JavDB/AI/MGDB 配置与 TTL。 */
export class Settings {
  readonly cacheTtlHours: number;
  readonly readyCacheLimit: number;
  readonly metadataConcurrency: number;
  readonly metadataTimeoutSeconds: number;
  readonly javdb: JavdbSettings;
  readonly ai: AiSettings;
  readonly mgdb: MgdbSettings;
  readonly providers: Map<string, ProviderState>;
  readonly avdbSync: AvdbSyncStatus;

  constructor(cacheTtlHours: number, readyCacheLimit: number, metadataConcurrency: number,
    metadataTimeoutSeconds: number, javdb: JavdbSettings, ai: AiSettings, mgdb: MgdbSettings,
    providers: Map<string, ProviderState>, avdbSync: AvdbSyncStatus) {
    this.cacheTtlHours = cacheTtlHours;
    this.readyCacheLimit = readyCacheLimit;
    this.metadataConcurrency = metadataConcurrency;
    this.metadataTimeoutSeconds = metadataTimeoutSeconds;
    this.javdb = javdb;
    this.ai = ai;
    this.mgdb = mgdb;
    this.providers = providers;
    this.avdbSync = avdbSync;
  }

  static fromText(text: string): Settings {
    const reader = JsonReader.fromText(text);
    const ttl = reader.number('cache_ttl_hours');
    if (ttl < 1 || ttl > 168 || Math.floor(ttl) !== ttl) {
      throw new ProtocolException('Settings.cache_ttl_hours out of range');
    }
    const readyLimit = reader.number('ready_cache_limit');
    const concurrency = reader.number('metadata_concurrency');
    const timeout = reader.number('metadata_timeout_seconds');
    if (readyLimit !== 20 || concurrency !== 3 || timeout !== 600) {
      throw new ProtocolException('Settings fixed limits are not 20/3/600');
    }
    const providers = new Map<string, ProviderState>();
    const providersRaw = reader.optionalObject('providers');
    if (providersRaw !== null) {
      for (const key of Object.keys(providersRaw)) {
        providers.set(key, ProviderState.fromReader(new JsonReader(providersRaw[key] as Record<string, Object>)));
      }
    }
    return new Settings(ttl, readyLimit, concurrency, timeout,
      JavdbSettings.fromReader(new JsonReader(reader.object('javdb'))),
      AiSettings.fromReader(new JsonReader(reader.object('ai'))),
      MgdbSettings.fromReader(new JsonReader(reader.object('mgdb'))),
      providers, AvdbSyncStatus.fromReader(new JsonReader(reader.object('avdb_sync'))));
  }
}

/** ConnectionTest：单一目标只读 probe 结果。 */
export class ConnectionTest {
  readonly target: string;
  readonly status: string;
  readonly errorCode: string | null;
  readonly elapsedMs: number;
  readonly checkedAt: string;

  constructor(target: string, status: string, errorCode: string | null, elapsedMs: number,
    checkedAt: string) {
    this.target = target;
    this.status = status;
    this.errorCode = errorCode;
    this.elapsedMs = elapsedMs;
    this.checkedAt = checkedAt;
  }

  static fromText(text: string): ConnectionTest {
    return ConnectionTest.fromReader(JsonReader.fromText(text));
  }

  static fromReader(reader: JsonReader): ConnectionTest {
    const target = reader.string('target');
    const targets: string[] = ['cloud115', 'javdb', 'dmm', 'gfriends', 'ai'];
    if (!targets.includes(target)) {
      throw new ProtocolException(`unexpected connection target: ${target}`);
    }
    const status = reader.string('status');
    const statuses: string[] = ['available', 'unavailable', 'credentials_invalid', 'not_configured'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected connection status: ${status}`);
    }
    return new ConnectionTest(target, status, reader.nullableString('error_code'),
      reader.number('elapsed_ms'), reader.dateTime('checked_at'));
  }
}

/** ComponentDiagnostic：组件状态。 */
export class ComponentDiagnostic {
  readonly component: string;
  readonly status: string;
  readonly errorCode: string | null;
  readonly checkedAt: string;

  constructor(component: string, status: string, errorCode: string | null, checkedAt: string) {
    this.component = component;
    this.status = status;
    this.errorCode = errorCode;
    this.checkedAt = checkedAt;
  }

  static fromReader(reader: JsonReader): ComponentDiagnostic {
    const component = reader.string('component');
    const components: string[] = ['api', 'scheduler', 'worker', 'postgres', 'avdb', 'javdb',
      'dmm', 'gfriends', 'ai', 'cloud115'];
    if (!components.includes(component)) {
      throw new ProtocolException(`unexpected component: ${component}`);
    }
    const status = reader.string('status');
    const statuses: string[] = ['healthy', 'degraded', 'unavailable', 'credentials_invalid', 'unknown'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected component status: ${status}`);
    }
    return new ComponentDiagnostic(component, status, reader.nullableString('error_code'),
      reader.dateTime('checked_at'));
  }
}

/** FailureDiagnostic：最近失败条目。 */
export class FailureDiagnostic {
  readonly taskType: string;
  readonly taskId: string;
  readonly errorCode: string;
  readonly attemptNo: number;
  readonly elapsedMs: number;
  readonly occurredAt: string;

  constructor(taskType: string, taskId: string, errorCode: string, attemptNo: number,
    elapsedMs: number, occurredAt: string) {
    this.taskType = taskType;
    this.taskId = taskId;
    this.errorCode = errorCode;
    this.attemptNo = attemptNo;
    this.elapsedMs = elapsedMs;
    this.occurredAt = occurredAt;
  }

  static fromReader(reader: JsonReader): FailureDiagnostic {
    const taskType = reader.string('task_type');
    if (taskType !== 'metadata' && taskType !== 'cache' && taskType !== 'sync' &&
      taskType !== 'credential') {
      throw new ProtocolException(`unexpected failure task_type: ${taskType}`);
    }
    return new FailureDiagnostic(taskType, reader.string('task_id'),
      reader.string('error_code'), reader.number('attempt_no'), reader.number('elapsed_ms'),
      reader.dateTime('occurred_at'));
  }
}

/** MetadataProgress：元数据总体进度（聚合视图）。 */
export class MetadataProgress {
  readonly total: number;
  readonly queued: number;
  readonly running: number;
  readonly completed: number;
  readonly failed: number;
  readonly finished: number;
  readonly currentNumbers: string[];

  constructor(total: number, queued: number, running: number, completed: number, failed: number,
    finished: number, currentNumbers: string[]) {
    this.total = total;
    this.queued = queued;
    this.running = running;
    this.completed = completed;
    this.failed = failed;
    this.finished = finished;
    this.currentNumbers = currentNumbers;
  }

  static fromReader(reader: JsonReader): MetadataProgress {
    const total = reader.number('total');
    const queued = reader.number('queued');
    const running = reader.number('running');
    const completed = reader.number('completed');
    const failed = reader.number('failed');
    const finished = reader.number('finished');
    if (running < 0 || running > 3) {
      throw new ProtocolException('MetadataProgress.running out of range');
    }
    if (total !== queued + running + completed + failed) {
      throw new ProtocolException('MetadataProgress totals are inconsistent');
    }
    if (finished !== completed + failed) {
      throw new ProtocolException('MetadataProgress.finished is inconsistent');
    }
    const currentNumbers = reader.stringArray('current_numbers');
    if (currentNumbers.length > 3 || !uniqueNonEmpty(currentNumbers)) {
      throw new ProtocolException('MetadataProgress.current_numbers is invalid');
    }
    if (currentNumbers.length !== running) {
      throw new ProtocolException('MetadataProgress.current_numbers length mismatch');
    }
    return new MetadataProgress(total, queued, running, completed, failed, finished, currentNumbers);
  }
}

/** MetadataQueueControl：元数据领取控制。 */
export class MetadataQueueControl {
  readonly paused: boolean;
  readonly queued: number;
  readonly running: number;

  constructor(paused: boolean, queued: number, running: number) {
    this.paused = paused;
    this.queued = queued;
    this.running = running;
  }

  static fromText(text: string): MetadataQueueControl {
    const reader = JsonReader.fromText(text);
    const running = reader.number('running');
    if (running < 0 || running > 3) {
      throw new ProtocolException('MetadataQueueControl.running out of range');
    }
    return new MetadataQueueControl(reader.boolean('paused'), reader.number('queued'), running);
  }
}

/** Diagnostics：脱敏诊断页数据。 */
export class Diagnostics {
  readonly generatedAt: string;
  readonly components: ComponentDiagnostic[];
  readonly queues: QueueDiagnostic;
  readonly metadataProgress: MetadataProgress;
  readonly recentFailures: FailureDiagnostic[];
  readonly connectionTests: ConnectionTest[];

  constructor(generatedAt: string, components: ComponentDiagnostic[], queues: QueueDiagnostic,
    metadataProgress: MetadataProgress, recentFailures: FailureDiagnostic[],
    connectionTests: ConnectionTest[]) {
    this.generatedAt = generatedAt;
    this.components = components;
    this.queues = queues;
    this.metadataProgress = metadataProgress;
    this.recentFailures = recentFailures;
    this.connectionTests = connectionTests;
  }

  static fromText(text: string): Diagnostics {
    const reader = JsonReader.fromText(text);
    const components: ComponentDiagnostic[] = [];
    const componentNames: string[] = [];
    for (const item of reader.objectArray('components')) {
      if (components.length >= 10) {
        throw new ProtocolException('Diagnostics.components exceeds limit');
      }
      const component = ComponentDiagnostic.fromReader(new JsonReader(item));
      if (componentNames.includes(component.component)) {
        throw new ProtocolException('Diagnostics.components has duplicates');
      }
      componentNames.push(component.component);
      components.push(component);
    }
    const failures: FailureDiagnostic[] = [];
    for (const item of reader.objectArray('recent_failures')) {
      if (failures.length >= 100) {
        throw new ProtocolException('Diagnostics.recent_failures exceeds limit');
      }
      failures.push(FailureDiagnostic.fromReader(new JsonReader(item)));
    }
    const tests: ConnectionTest[] = [];
    const targets: string[] = [];
    for (const item of reader.objectArray('connection_tests')) {
      if (tests.length >= 5) {
        throw new ProtocolException('Diagnostics.connection_tests exceeds limit');
      }
      const test = ConnectionTest.fromReader(new JsonReader(item));
      if (targets.includes(test.target)) {
        throw new ProtocolException('Diagnostics.connection_tests has duplicates');
      }
      targets.push(test.target);
      tests.push(test);
    }
    return new Diagnostics(reader.dateTime('generated_at'), components,
      QueueDiagnostic.fromReader(new JsonReader(reader.object('queues'))),
      MetadataProgress.fromReader(new JsonReader(reader.object('metadata_progress'))),
      failures, tests);
  }
}

/** MetadataRetryResult：retry/retry-enrichment 201 响应。 */
export class MetadataRetryResult {
  readonly id: string;
  readonly number: string;
  readonly status: string;
  readonly attemptNo: number;
  readonly requestedStages: string[];
  readonly retryableStages: string[];
  readonly createdAt: string;

  constructor(id: string, number: string, status: string, attemptNo: number,
    requestedStages: string[], retryableStages: string[], createdAt: string) {
    this.id = id;
    this.number = number;
    this.status = status;
    this.attemptNo = attemptNo;
    this.requestedStages = requestedStages;
    this.retryableStages = retryableStages;
    this.createdAt = createdAt;
  }

  static fromText(text: string): MetadataRetryResult {
    const reader = JsonReader.fromText(text);
    const id = reader.string('id');
    if (!SOURCE_UUID_PATTERN.test(id)) {
      throw new ProtocolException('MetadataRetryResult.id is not a uuid');
    }
    return new MetadataRetryResult(id, reader.string('number'), reader.string('status'),
      reader.number('attempt_no'), reader.stringArray('requested_stages'),
      reader.stringArray('retryable_stages'), reader.dateTime('created_at'));
  }
}

/** MetadataStageDto：单阶段执行状态（javdb_core 不可单独重试）。 */
export class MetadataStageDto {
  readonly stage: string;
  readonly status: string;
  readonly errorCode: string | null;

  constructor(stage: string, status: string, errorCode: string | null) {
    this.stage = stage;
    this.status = status;
    this.errorCode = errorCode;
  }

  static fromReader(reader: JsonReader): MetadataStageDto {
    const stage = reader.string('stage');
    const stages: string[] = ['javdb_core', 'images', 'dmm', 'actor_map', 'gfriends', 'translation'];
    if (!stages.includes(stage)) {
      throw new ProtocolException(`unexpected metadata stage: ${stage}`);
    }
    const status = reader.string('status');
    const statuses: string[] = ['pending', 'running', 'succeeded', 'warning', 'failed', 'skipped'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected stage status: ${status}`);
    }
    return new MetadataStageDto(stage, status, reader.nullableString('error_code'));
  }
}

/** MetadataJobFull：/admin/metadata-jobs 任务（含 retryable_stages 白名单）。 */
export class MetadataJobFull {
  readonly id: string;
  readonly number: string;
  readonly status: string;
  readonly attemptNo: number;
  readonly retryMode: string;
  readonly requestedStages: string[];
  readonly retryableStages: string[];
  readonly stages: MetadataStageDto[];
  readonly errorCode: string | null;
  readonly createdAt: string;

  constructor(id: string, number: string, status: string, attemptNo: number, retryMode: string,
    requestedStages: string[], retryableStages: string[], stages: MetadataStageDto[],
    errorCode: string | null, createdAt: string) {
    this.id = id;
    this.number = number;
    this.status = status;
    this.attemptNo = attemptNo;
    this.retryMode = retryMode;
    this.requestedStages = requestedStages;
    this.retryableStages = retryableStages;
    this.stages = stages;
    this.errorCode = errorCode;
    this.createdAt = createdAt;
  }

  /** 可富化重试：completed_with_warnings 或 failed 且有可选阶段（永不包含 javdb_core）。 */
  canRetryEnrichment(): boolean {
    if (this.status !== 'completed_with_warnings' && this.status !== 'failed') {
      return false;
    }
    return this.retryableStages.length > 0;
  }

  static fromReader(reader: JsonReader): MetadataJobFull {
    const id = reader.string('id');
    if (!SOURCE_UUID_PATTERN.test(id)) {
      throw new ProtocolException('MetadataJobFull.id is not a uuid');
    }
    const status = reader.string('status');
    const statuses: string[] = ['queued', 'running', 'completed', 'completed_with_warnings', 'failed'];
    if (!statuses.includes(status)) {
      throw new ProtocolException(`unexpected metadata job status: ${status}`);
    }
    const stages: MetadataStageDto[] = [];
    for (const item of reader.objectArray('stages')) {
      stages.push(MetadataStageDto.fromReader(new JsonReader(item)));
    }
    const retryableStages = reader.stringArray('retryable_stages');
    const enrichment: string[] = ['images', 'dmm', 'actor_map', 'gfriends', 'translation'];
    for (const stage of retryableStages) {
      if (!enrichment.includes(stage)) {
        throw new ProtocolException(`unexpected retryable stage: ${stage}`);
      }
    }
    return new MetadataJobFull(id, reader.string('number'), status, reader.number('attempt_no'),
      reader.string('retry_mode'), reader.stringArray('requested_stages'), retryableStages,
      stages, reader.nullableString('error_code'), reader.dateTime('created_at'));
  }
}

/** MetadataJobPage：持久元数据队列快照。 */
export class MetadataJobPage {
  readonly items: MetadataJobFull[];
  readonly nextCursor: string | null;

  constructor(items: MetadataJobFull[], nextCursor: string | null) {
    this.items = items;
    this.nextCursor = nextCursor;
  }

  static fromText(text: string): MetadataJobPage {
    const reader = JsonReader.fromText(text);
    const items: MetadataJobFull[] = [];
    const ids: string[] = [];
    for (const item of reader.objectArray('items')) {
      if (items.length >= 100) {
        throw new ProtocolException('MetadataJobPage.items exceeds limit');
      }
      const job = MetadataJobFull.fromReader(new JsonReader(item));
      if (ids.includes(job.id)) {
        throw new ProtocolException('MetadataJobPage.items has duplicate ids');
      }
      ids.push(job.id);
      items.push(job);
    }
    return new MetadataJobPage(items, reader.nullableString('next_cursor'));
  }
}

/** PlayRequestResult：/movies/{id}/play-requests 响应（AC-084/087/089/091）。 */
export class PlayRequestResult {
  readonly disposition: string;
  readonly waitDeadline: string | null;
  readonly cacheJob: CacheJobDetail;

  constructor(disposition: string, waitDeadline: string | null, cacheJob: CacheJobDetail) {
    this.disposition = disposition;
    this.waitDeadline = waitDeadline;
    this.cacheJob = cacheJob;
  }

  static fromText(text: string): PlayRequestResult {
    const reader = JsonReader.fromText(text);
    const disposition = reader.string('disposition');
    const dispositions: string[] = ['ready', 'started', 'queued', 'reused'];
    if (!dispositions.includes(disposition)) {
      throw new ProtocolException(`unexpected play disposition: ${disposition}`);
    }
    const deadline = reader.nullableString('wait_deadline');
    const job = CacheJobDetail.fromReader(new JsonReader(reader.object('cache_job')));
    if (disposition === 'started') {
      if (deadline === null) {
        throw new ProtocolException('started disposition requires wait_deadline');
      }
      if (job.status !== 'submitting') {
        throw new ProtocolException('started disposition requires submitting cache job');
      }
    } else if (deadline !== null) {
      throw new ProtocolException('wait_deadline is only allowed for started');
    }
    if (disposition === 'ready' && job.status !== 'ready') {
      throw new ProtocolException('ready disposition requires ready cache job');
    }
    if (disposition === 'queued' && job.status !== 'queued') {
      throw new ProtocolException('queued disposition requires queued cache job');
    }
    return new PlayRequestResult(disposition, deadline, job);
  }
}
