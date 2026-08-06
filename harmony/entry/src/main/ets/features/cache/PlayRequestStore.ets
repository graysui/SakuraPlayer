/**
 * 播放请求 Store（AC-084..091、AC-117）。
 *
 * - 只有用户点播放才 submit（POST /movies/{id}/play-requests + Idempotency-Key）；
 *   重复点击在途 single-flight，响应后再次点击依赖服务端活动任务复用。
 * - started → WAITING 全屏锁：服务端 wait_deadline 换算剩余 0..60 秒（Date.now 近似单调），
 *   1s 倒计时；60 秒内 snapshot 同 job ready → READY 自动播放（一次，navigationRevision 去重）。
 * - 60 秒后 → TIMED_OUT（只退状态，不调任何取消 API，任务继续在 115 后台执行）。
 * - queued → 立即退出等待提示排队；reused+ready → READY；reused+其他 → EXISTING。
 * - 取消：页面二次确认后 cancel({confirmed:true})；成功 CANCELLED；稳定错误保留 WAITING。
 * - 页面销毁：detach 清 timer/listener；后台 ready 不自动导航。
 */

import { util } from '@kit.ArkTS';
import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, CacheJobDetail, PlayRequestResult } from '../../core/api/ApiModels';
import { SnapshotStore } from '../../core/events/SnapshotStore';

export enum PlayRequestPhase {
  IDLE,
  SUBMITTING,
  WAITING,
  QUEUED,
  EXISTING,
  READY,
  TIMED_OUT,
  CANCELLED,
  FAILED,
}

@ObservedV2
export class PlayRequestStore {
  @Trace phase: PlayRequestPhase = PlayRequestPhase.IDLE;
  @Trace movieId: string | null = null;
  @Trace sourceId: string | null = null;
  @Trace job: CacheJobDetail | null = null;
  @Trace remainingSeconds: number = 0;
  @Trace errorCode: string | null = null;
  @Trace cancelError: string | null = null;
  @Trace cancelling: boolean = false;
  /** ready 事件自增（页面据此区分"新就绪"并导航一次）。 */
  navigationRevision: number = 0;

  private apiClient: ApiClient | null = null;
  private snapshot: SnapshotStore | null = null;
  private submittingInFlight: boolean = false;
  private deadlineMs: number = -1;
  private timer: number | null = null;
  private readonly snapshotListener: () => void = (): void => {
    this.applySnapshot();
  };
  private readonly changeListeners: (() => void)[] = [];

  attach(client: ApiClient | null, snapshot: SnapshotStore | null): void {
    this.apiClient = client;
    if (this.snapshot !== null) {
      this.snapshot.removeListener(this.snapshotListener);
    }
    this.snapshot = snapshot;
    if (snapshot !== null) {
      snapshot.addListener(this.snapshotListener);
    }
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

  /** 页面销毁/认证变化：清 timer/listener 与在途状态（后台任务继续）。 */
  detach(): void {
    this.apiClient = null;
    if (this.snapshot !== null) {
      this.snapshot.removeListener(this.snapshotListener);
      this.snapshot = null;
    }
    this.stopTimer();
    this.submittingInFlight = false;
    this.phase = PlayRequestPhase.IDLE;
    this.movieId = null;
    this.sourceId = null;
    this.job = null;
    this.remainingSeconds = 0;
    this.errorCode = null;
    this.cancelError = null;
    this.cancelling = false;
    this.deadlineMs = -1;
    this.notifyChanged();
  }

  /** 用户点击播放：single-flight；在途返回。 */
  submit(movieId: string, sourceId: string): void {
    if (this.submittingInFlight) {
      return;
    }
    const client = this.apiClient;
    if (client === null) {
      this.phase = PlayRequestPhase.FAILED;
      this.errorCode = 'client_transport_error';
      this.notifyChanged();
      return;
    }
    this.submittingInFlight = true;
    this.movieId = movieId;
    this.sourceId = sourceId;
    this.phase = PlayRequestPhase.SUBMITTING;
    this.errorCode = null;
    this.cancelError = null;
    this.job = null;
    this.deadlineMs = -1;
    this.stopTimer();
    this.notifyChanged();
    const idempotencyKey = PlayRequestStore.newIdempotencyKey();
    client.createPlayRequest(movieId, sourceId, idempotencyKey).then((result: PlayRequestResult) => {
      this.submittingInFlight = false;
      this.applyResult(result);
    }).catch((err: Error) => {
      this.submittingInFlight = false;
      this.phase = PlayRequestPhase.FAILED;
      this.errorCode = this.errorCodeOf(err);
      this.notifyChanged();
    });
  }

  /** 取消（页面二次确认后）：成功 CANCELLED，稳定错误保留 WAITING。 */
  cancel(confirmed: boolean): void {
    const job = this.job;
    const client = this.apiClient;
    if (!confirmed || this.phase !== PlayRequestPhase.WAITING || job === null || client === null) {
      return;
    }
    if (this.cancelling) {
      return;
    }
    this.cancelling = true;
    this.cancelError = null;
    this.notifyChanged();
    client.cancelCacheJob(job.id).then((updated: CacheJobDetail) => {
      this.cancelling = false;
      this.stopTimer();
      this.job = updated;
      if (updated.status === 'ready') {
        // 取消在途时任务恰好完成：按服务端真相修正为 READY
        this.phase = PlayRequestPhase.READY;
        this.navigationRevision++;
      } else {
        this.phase = PlayRequestPhase.CANCELLED;
      }
      this.notifyChanged();
    }).catch((err: Error) => {
      this.cancelling = false;
      // 稳定错误保留等待页；取消按钮重新可用
      this.cancelError = this.errorCodeOf(err);
      this.notifyChanged();
    });
  }

  /** 重置（等待结束/导航后由页面调用）。 */
  reset(): void {
    this.stopTimer();
    this.phase = PlayRequestPhase.IDLE;
    this.movieId = null;
    this.sourceId = null;
    this.job = null;
    this.remainingSeconds = 0;
    this.errorCode = null;
    this.cancelError = null;
    this.cancelling = false;
    this.deadlineMs = -1;
    this.notifyChanged();
  }

  private applyResult(result: PlayRequestResult): void {
    this.job = result.cacheJob;
    if (result.disposition === 'started') {
      this.startWaiting(result);
    } else if (result.disposition === 'queued') {
      this.phase = PlayRequestPhase.QUEUED;
      this.notifyChanged();
    } else if (result.disposition === 'ready') {
      this.phase = PlayRequestPhase.READY;
      this.navigationRevision++;
      this.notifyChanged();
    } else {
      // reused
      if (result.cacheJob.status === 'ready') {
        this.phase = PlayRequestPhase.READY;
        this.navigationRevision++;
      } else {
        this.phase = PlayRequestPhase.EXISTING;
      }
      this.notifyChanged();
    }
  }

  private startWaiting(result: PlayRequestResult): void {
    const deadline = result.waitDeadline;
    if (deadline === null) {
      this.phase = PlayRequestPhase.FAILED;
      this.errorCode = 'client_protocol_error';
      this.notifyChanged();
      return;
    }
    const wallNow = Date.now();
    let remainingMs = Date.parse(deadline) - wallNow;
    if (Number.isNaN(remainingMs)) {
      this.phase = PlayRequestPhase.FAILED;
      this.errorCode = 'client_protocol_error';
      this.notifyChanged();
      return;
    }
    if (remainingMs < 0) {
      remainingMs = 0;
    }
    const maxMs = 60000;
    if (remainingMs > maxMs) {
      remainingMs = maxMs;
    }
    this.deadlineMs = wallNow + remainingMs;
    if (remainingMs <= 0) {
      // deadline 已过：直接超时（服务端任务继续）
      this.phase = PlayRequestPhase.TIMED_OUT;
      this.remainingSeconds = 0;
      this.notifyChanged();
      return;
    }
    this.phase = PlayRequestPhase.WAITING;
    this.remainingSeconds = Math.ceil(remainingMs / 1000);
    this.notifyChanged();
    this.startTimer();
  }

  private startTimer(): void {
    if (this.timer !== null) {
      return;
    }
    this.timer = setInterval(() => {
      this.onTick();
    }, 1000);
  }

  private stopTimer(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private onTick(): void {
    if (this.phase !== PlayRequestPhase.WAITING) {
      this.stopTimer();
      return;
    }
    const remainingMs = this.deadlineMs - Date.now();
    if (remainingMs <= 0) {
      // 60 秒超时：只退状态，不调用任何取消 API；任务继续在 115 后台执行
      this.stopTimer();
      this.phase = PlayRequestPhase.TIMED_OUT;
      this.remainingSeconds = 0;
      this.notifyChanged();
      return;
    }
    const next = Math.ceil(remainingMs / 1000);
    if (next !== this.remainingSeconds) {
      this.remainingSeconds = next;
      this.notifyChanged();
    }
  }

  /** 评估 snapshot job 的终态动作（纯逻辑可测）：
   *  auto_play / timeout / failed / existing / cancelled / ignore。 */
  static evaluateSnapshot(phase: PlayRequestPhase, jobId: string | null, deadlineMs: number,
    nowMs: number, updatedId: string | null, updatedStatus: string,
    updatedErrorCode: string | null): string {
    if (phase !== PlayRequestPhase.WAITING || jobId === null || updatedId === null ||
      jobId !== updatedId) {
      return 'ignore';
    }
    if (updatedStatus === 'ready') {
      if (nowMs < deadlineMs) {
        return 'auto_play';
      }
      return 'timeout';
    }
    if (updatedStatus === 'failed') {
      return 'failed';
    }
    if (updatedStatus === 'awaiting_selection') {
      return 'existing';
    }
    // cleaned/cleanup_failed/detached 不改变 60 秒本地计时（契约 §4）
    return 'ignore';
  }

  /** snapshot 监听：仅 WAITING 且同 job 时评估 ready/failed/其他终态。 */
  private applySnapshot(): void {
    const job = this.job;
    if (this.phase !== PlayRequestPhase.WAITING || job === null || this.cancelling) {
      // cancelling 在途：冻结 auto_play（避免导航到已取消任务）
      return;
    }
    const snapshot = this.snapshot;
    if (snapshot === null) {
      return;
    }
    let updatedId: string | null = null;
    let updatedStatus: string = '';
    let updatedError: string | null = null;
    for (const item of snapshot.cacheJobList) {
      if (item.id === job.id) {
        updatedId = item.id;
        updatedStatus = item.status;
        updatedError = item.errorCode;
        break;
      }
    }
    if (updatedId === null) {
      return;
    }
    const action = PlayRequestStore.evaluateSnapshot(this.phase, job.id,
      this.deadlineMs, Date.now(), updatedId, updatedStatus, updatedError);
    if (action === 'auto_play') {
      // 60 秒内完成：自动播放一次
      this.stopTimer();
      this.phase = PlayRequestPhase.READY;
      this.navigationRevision++;
      this.notifyChanged();
    } else if (action === 'timeout') {
      // deadline 后 ready：不自动播放，走超时
      this.onTick();
    } else if (action === 'failed') {
      this.stopTimer();
      this.phase = PlayRequestPhase.FAILED;
      this.errorCode = updatedError ?? 'cache_failed';
      this.notifyChanged();
    } else if (action === 'existing') {
      this.stopTimer();
      this.phase = PlayRequestPhase.EXISTING;
      this.notifyChanged();
    }
  }

  private errorCodeOf(err: Error): string {
    if (err instanceof ApiException) {
      return err.code;
    }
    return 'client_transport_error';
  }

  /** 幂等键：UUIDv4（加密随机，36 字符含连字符，16..128 安全 ASCII）。 */
  static newIdempotencyKey(): string {
    return util.generateRandomUUID();
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}
