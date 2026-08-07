/**
 * 进度 Store（AC-111/112/113、TASK-111 契约）。
 *
 * - 15 秒心跳（playing=true 续租 + 可选进度 CAS）；pause/exit flush（playing=false 结束 lease）。
 * - expected-version CAS：PUT /movies/{id}/progress 与心跳携带 expected version；
 *   409 progress_version_conflict 用 details.progress 权威版本覆盖并重试一次（不循环）。
 * - 完成规则（95%/2 分钟）后端权威：客户端只上报 position/duration，用响应更新本地。
 * - 无进度心跳（progress 可省略）；未知时长 duration 用 null（不能 0）。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, JsonReader, PlaybackProgress, ProgressUpdateBody } from '../../core/api/ApiModels';

@ObservedV2
export class ProgressStore {
  @Trace version: number = 0;
  @Trace authoritative: PlaybackProgress | null = null;
  @Trace lastError: string | null = null;
  @Trace heartbeating: boolean = false;
  @Trace completed: boolean = false;

  private static readonly HEARTBEAT_MS = 15000;

  private apiClient: ApiClient | null = null;
  private sessionId: string = '';
  private movieId: string = '';
  private clientInstanceId: string = '';
  private timer: number | null = null;
  private stopped: boolean = true;
  private latestPositionMs: number = 0;
  private latestDurationMs: number = 0;
  private retryCount: number = 0;
  private readonly changeListeners: (() => void)[] = [];

  attach(client: ApiClient | null, sessionId: string, movieId: string,
    clientInstanceId: string): void {
    this.apiClient = client;
    this.sessionId = sessionId;
    this.movieId = movieId;
    this.clientInstanceId = clientInstanceId;
  }

  addChangeListener(listener: () => void): void {
    if (!this.changeListeners.includes(listener)) {
      this.changeListeners.push(listener);
    }
  }

  removeChangeListener(listener: () => void): void {
    const index = this.changeListeners.indexOf(listener);
    if (index >= 0) {
      this.changeListeners.splice(index, 1);
    }
  }

  /** 进入播放：初始 version 来自 manifest 权威进度（无则 0）；启动 15 秒心跳。 */
  start(initial: PlaybackProgress | null): void {
    this.retryCount = 0;
    this.version = initial !== null ? initial.version : 0;
    this.authoritative = initial;
    this.completed = initial !== null && initial.completed;
    this.stopped = false;
    this.lastError = null;
    this.heartbeating = true;
    this.notifyChanged();
    if (this.timer === null) {
      this.timer = setInterval(() => {
        this.onHeartbeatTick();
      }, ProgressStore.HEARTBEAT_MS);
    }
  }

  /** 最新播放进度（PlayerPage timeUpdate 上报；心跳带进度执行影片状态 CAS）。 */
  setLatestProgress(positionMs: number, durationMs: number): void {
    this.latestPositionMs = positionMs;
    if (durationMs > 0) {
      this.latestDurationMs = durationMs;
    }
  }

  /** 15 秒心跳：携带最新进度续租（playing=true）。 */
  private onHeartbeatTick(): void {
    if (this.stopped) {
      return;
    }
    this.heartbeat(this.latestBody(), true).catch(() => {
      // 心跳失败不阻塞播放；下个周期重试
    });
  }

  private latestBody(): ProgressUpdateBody | null {
    const duration = this.latestDurationMs > 0 ? this.latestDurationMs / 1000 : null;
    const position = this.latestPositionMs / 1000;
    if (position <= 0 && duration === null) {
      return null; // 无进度：纯续租
    }
    return new ProgressUpdateBody(position, duration, this.version);
  }

  /** 心跳：progress 可省略；playing=false 结束 lease（pause/exit flush）。 */
  async heartbeat(progress: ProgressUpdateBody | null, playing: boolean): Promise<void> {
    const client = this.apiClient;
    if (client === null || this.sessionId.length === 0) {
      return;
    }
    const progressJson = progress === null ? null : JSON.stringify({
      'position_seconds': progress.positionSeconds,
      'duration_seconds': progress.durationSeconds,
      'version': progress.version,
    });
    try {
      const result = await client.heartbeatPlaybackSession(this.sessionId, this.clientInstanceId,
        progressJson, playing);
      if (result.progress !== null) {
        this.applyAuthoritative(result.progress);
      }
      this.lastError = null;
    } catch (err) {
      this.handleHeartbeatError(err, progress, playing);
    }
  }

  /** 携带进度提交（心跳带 progress 或单独 flush 给 pause/exit）。 */
  async submit(progress: ProgressUpdateBody): Promise<void> {
    await this.heartbeat(progress, true);
  }

  /** pause/exit flush：playing=false 结束 lease + 最新进度 CAS（不要求伪造心跳）。 */
  async flush(): Promise<void> {
    await this.heartbeat(this.latestBody(), false);
  }

  /** 暂停：停 15 秒心跳并 flush（playing=false 结束 lease；避免 pause 后心跳以
   *  playing=true 重新续租）。 */
  pause(): void {
    this.stopped = true;
    this.heartbeating = false;
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.flush().catch(() => {
      // flush 失败忽略
    });
    this.notifyChanged();
  }

  /** 恢复播放：重启 15 秒心跳（version 已由 start/flush 保持）。 */
  resume(): void {
    if (!this.stopped) {
      return;
    }
    this.stopped = false;
    this.heartbeating = true;
    if (this.timer === null) {
      this.timer = setInterval(() => {
        this.onHeartbeatTick();
      }, ProgressStore.HEARTBEAT_MS);
    }
    this.notifyChanged();
  }

  /** 停止心跳（页面销毁/会话失效）。 */
  stop(): void {
    this.stopped = true;
    this.heartbeating = false;
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.notifyChanged();
  }

  private handleHeartbeatError(err: Error, progress: ProgressUpdateBody | null,
    playing: boolean): void {
    if (err instanceof ApiException && err.code === 'progress_version_conflict') {
      // 409：details.progress 携带权威状态；覆盖本地 version 后至多重试一次（不循环）
      const authoritative = this.extractAuthoritative(err);
      if (authoritative !== null) {
        this.applyAuthoritative(authoritative);
      }
      if (this.retryCount === 0 && progress !== null && !this.stopped) {
        this.retryCount = 1;
        const retry = new ProgressUpdateBody(progress.positionSeconds, progress.durationSeconds,
          this.version);
        this.heartbeat(retry, playing).catch(() => {
          this.lastError = 'progress_version_conflict';
          this.notifyChanged();
        });
        return;
      }
      this.lastError = 'progress_version_conflict';
      this.notifyChanged();
      return;
    }
    if (err instanceof ApiException && err.code === 'state_conflict') {
      // 会话/租约失效：停止心跳（不循环重试）
      this.stop();
      this.lastError = 'state_conflict';
      this.notifyChanged();
      return;
    }
    this.lastError = err instanceof ApiException ? err.code : 'client_transport_error';
    this.notifyChanged();
  }

  /** 从 409 details 提取权威进度。 */
  private extractAuthoritative(err: ApiException): PlaybackProgress | null {
    try {
      const details = err.details;
      if (details === null) {
        return null;
      }
      const parsed = JSON.parse(details) as Record<string, Object>;
      const raw = parsed['progress'];
      if (typeof raw !== 'object' || raw === null) {
        return null;
      }
      const progress = PlaybackProgress.fromReader(JsonReader.fromText(JSON.stringify(raw)));
      // 纵深防御：版本/位置数值钳制（畸形权威不采纳）
      if (progress.version < 0 || progress.positionSeconds < 0) {
        return null;
      }
      return progress;
    } catch (e) {
      return null;
    }
  }

  private applyAuthoritative(progress: PlaybackProgress): void {
    this.authoritative = progress;
    this.version = progress.version;
    this.completed = progress.completed;
    this.notifyChanged();
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}
