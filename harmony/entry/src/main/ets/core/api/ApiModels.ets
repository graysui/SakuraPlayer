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
  readonly status: string;
  readonly lastVerifiedAt: string | null;

  constructor(status: string, lastVerifiedAt: string | null) {
    this.status = status;
    this.lastVerifiedAt = lastVerifiedAt;
  }

  static fromReader(reader: JsonReader): Cloud115Binding {
    return new Cloud115Binding(reader.string('status'), reader.nullableDateTime('last_verified_at'));
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
    return new QueueDiagnostic(
      reader.number('metadata_queued'),
      reader.number('metadata_running'),
      reader.boolean('metadata_paused'),
      reader.number('cache_queued'),
      reader.number('cache_running'),
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
