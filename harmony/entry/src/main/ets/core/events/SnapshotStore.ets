/**
 * 实时事件信封与 REST 快照合并（realtime-events.md 契约）。
 *
 * 合并算法：
 * 1. event_id 已处理或 sequence <= snapshot_version → 忽略。
 * 2. 已建立聚合版本基线时，同资源 stream_version <= local_version → 忽略。
 * 3. 合法顺序事件按字段浅合并 resource；null 权威清空，数组整体替换。
 * 4. 跳号、未知版本、字段形状非法或本地无资源 → 拉 REST 快照恢复。
 */

import { ApiClient } from '../api/ApiClient';
import { CacheJob, EventSnapshot, JsonReader, Notification, ProtocolException } from '../api/ApiModels';

/** 事件信封（版本 1）。 */
export class EventEnvelope {
  readonly version: number;
  readonly eventId: string;
  readonly sequence: number;
  readonly stream: string;
  readonly streamVersion: number;
  readonly type: string;
  readonly occurredAt: string;
  readonly resource: Record<string, Object> | null;

  constructor(version: number, eventId: string, sequence: number, stream: string,
    streamVersion: number, type: string, occurredAt: string, resource: Record<string, Object> | null) {
    this.version = version;
    this.eventId = eventId;
    this.sequence = sequence;
    this.stream = stream;
    this.streamVersion = streamVersion;
    this.type = type;
    this.occurredAt = occurredAt;
    this.resource = resource;
  }

  static fromText(text: string): EventEnvelope {
    const reader = JsonReader.fromText(text);
    if (reader.number('version') !== 1) {
      throw new ProtocolException(`unsupported envelope version`);
    }
    return new EventEnvelope(
      1,
      reader.string('event_id'),
      reader.number('sequence'),
      reader.string('stream'),
      reader.number('stream_version'),
      reader.string('type'),
      reader.dateTime('occurred_at'),
      reader.nullableObject('resource'));
  }
}

/** apply 结果三态。 */
export enum EventApplyResult {
  APPLIED,
  IGNORED,
  RECOVERED,
}

/** 合并后资源变化监听（供 UI 层订阅；命名回调可注销）。 */
export type SnapshotListener = () => void;

/** 快照合并器：维护游标、聚合版本与资源表，驱动 REST 恢复。 */
export class SnapshotStore {
  private apiClient: ApiClient;
  private snapshotVersion: number = 0;
  private lastEventId: string | null = null;
  private readonly seenEventIds: string[] = [];
  private readonly cacheJobs: Map<string, CacheJob> = new Map();
  private readonly metadataJobIds: string[] = [];
  private readonly notifications: Map<string, Notification> = new Map();
  private readonly resourceVersions: Map<string, number> = new Map();
  private readonly listeners: SnapshotListener[] = [];
  private readonly MAX_SEEN = 2048;

  constructor(apiClient: ApiClient) {
    this.apiClient = apiClient;
  }

  get version(): number {
    return this.snapshotVersion;
  }

  get cursor(): string | null {
    return this.lastEventId;
  }

  get cacheJobList(): CacheJob[] {
    const result: CacheJob[] = [];
    this.cacheJobs.forEach((job) => result.push(job));
    return result;
  }

  get notificationList(): Notification[] {
    const result: Notification[] = [];
    this.notifications.forEach((notification) => result.push(notification));
    return result;
  }

  /** 事件去重：已见则忽略。 */
  private rememberEventId(eventId: string): boolean {
    if (this.seenEventIds.includes(eventId)) {
      return true;
    }
    this.seenEventIds.push(eventId);
    if (this.seenEventIds.length > this.MAX_SEEN) {
      this.seenEventIds.shift();
    }
    return false;
  }

  /** 应用一个事件；返回三态。 */
  apply(envelope: EventEnvelope): EventApplyResult {
    if (this.rememberEventId(envelope.eventId)) {
      return EventApplyResult.IGNORED;
    }
    if (envelope.sequence <= this.snapshotVersion) {
      return EventApplyResult.IGNORED;
    }
    // 游标推进必须连续；跳号拉快照
    if (envelope.sequence !== this.snapshotVersion + 1) {
      return EventApplyResult.RECOVERED;
    }
    const resourceId = this.resourceIdOf(envelope);
    if (resourceId === null) {
      // 无资源的信封（如 ping/pong 不会到达；未知类型）→ 推进游标并触发恢复
      this.snapshotVersion = envelope.sequence;
      this.lastEventId = envelope.eventId;
      return EventApplyResult.RECOVERED;
    }
    const localVersion = this.resourceVersions.get(resourceId);
    if (localVersion !== undefined) {
      if (envelope.streamVersion <= localVersion) {
        // 过期事件：忽略但推进游标
        this.snapshotVersion = envelope.sequence;
        this.lastEventId = envelope.eventId;
        return EventApplyResult.IGNORED;
      }
      if (envelope.streamVersion !== localVersion + 1) {
        return EventApplyResult.RECOVERED;
      }
    }
    if (!this.hasResource(envelope.stream, resourceId)) {
      return EventApplyResult.RECOVERED;
    }
    // 合法顺序事件：浅合并
    if (!this.mergeResource(envelope)) {
      return EventApplyResult.RECOVERED;
    }
    this.snapshotVersion = envelope.sequence;
    this.lastEventId = envelope.eventId;
    this.resourceVersions.set(resourceId, envelope.streamVersion);
    this.notifyChanged();
    return EventApplyResult.APPLIED;
  }

  private resourceIdOf(envelope: EventEnvelope): string | null {
    if (envelope.resource === null) {
      return null;
    }
    const id = envelope.resource['id'];
    return typeof id === 'string' ? id : null;
  }

  private hasResource(stream: string, resourceId: string): boolean {
    if (stream === 'cache') {
      return this.cacheJobs.has(resourceId);
    }
    if (stream === 'notification') {
      return this.notifications.has(resourceId);
    }
    return false;
  }

  /** 字段级浅合并；返回 false 表示形状非法需恢复。 */
  private mergeResource(envelope: EventEnvelope): boolean {
    const resource = envelope.resource;
    if (resource === null) {
      return false;
    }
    try {
      if (envelope.stream === 'cache') {
        const base = this.cacheJobs.get(resource['id'] as string);
        if (base === undefined) {
          return false;
        }
        this.cacheJobs.set(base.id, CacheJob.mergePatch(base, new JsonReader(resource)));
        return true;
      }
      if (envelope.stream === 'notification') {
        const base = this.notifications.get(resource['id'] as string);
        if (base === undefined) {
          return false;
        }
        this.notifications.set(base.id, Notification.mergePatch(base, new JsonReader(resource)));
        return true;
      }
      // metadata/credential/catalog：TASK-302 只跟踪版本，字段合并由后续任务细化
      return true;
    } catch (err) {
      return false;
    }
  }

  /** REST 快照恢复：重建全状态与版本表，清空去重集。 */
  async recover(): Promise<boolean> {
    let snapshot: EventSnapshot;
    try {
      snapshot = await this.apiClient.getEventSnapshot();
    } catch (err) {
      return false;
    }
    this.snapshotVersion = snapshot.snapshotVersion;
    this.lastEventId = snapshot.lastEventId;
    this.seenEventIds.length = 0;
    this.cacheJobs.clear();
    this.resourceVersions.clear();
    this.notifications.clear();
    this.metadataJobIds.length = 0;
    for (const job of snapshot.cacheJobs) {
      this.cacheJobs.set(job.id, job);
    }
    for (const job of snapshot.metadataJobs) {
      this.metadataJobIds.push(job.id);
    }
    for (const notification of snapshot.notifications) {
      this.notifications.set(notification.id, notification);
    }
    this.notifyChanged();
    return true;
  }

  /** 本地缺少资源时补齐（未知资源事件 → 恢复后重放逻辑由调用方决定）。 */
  addResourceFromSnapshot(stream: string, resource: Object): void {
    if (stream === 'cache' && resource instanceof CacheJob) {
      this.cacheJobs.set(resource.id, resource);
    }
  }

  addListener(listener: SnapshotListener): void {
    if (!this.listeners.includes(listener)) {
      this.listeners.push(listener);
    }
  }

  removeListener(listener: SnapshotListener): void {
    const index = this.listeners.indexOf(listener);
    if (index >= 0) {
      this.listeners.splice(index, 1);
    }
  }

  private notifyChanged(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }
}
