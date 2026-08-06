/**
 * 缓存页 Store（AC-118/122）。
 *
 * - 每页 24 项，容量固定 running 2/queued 10/ready 20 + 服务端当前计数。
 * - 取消只对 queued/submitting/offlining/submit_uncertain/resolving，页面先二次确认再
 *   发送 {confirmed:true}；202 响应替换列表项（不重拉）。
 * - 清理只对 awaiting_selection/ready/cleanup_failed；cache_active_lease 保留原任务并
 *   提示正在播放；cache_ownership_mismatch 显示已失联。
 * - cancelling/cleaning 不提供重复操作；failed/cleaned/detached 只读。
 * - 事件快照变化触发当前列表刷新（列表 API 仍是分页真相）。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, CacheCapacity, CacheJobDetail, CacheJobPage } from '../../core/api/ApiModels';
import { SnapshotListener, SnapshotStore } from '../../core/events/SnapshotStore';

export enum CachePageStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
}

@ObservedV2
export class CacheStore {
  @Trace status: CachePageStatus = CachePageStatus.IDLE;
  @Trace items: CacheJobDetail[] = [];
  @Trace capacity: CacheCapacity | null = null;
  @Trace nextCursor: string | null = null;
  @Trace loadingMore: boolean = false;
  @Trace actionJobId: string | null = null;
  @Trace actionError: string | null = null;
  @Trace errorMessage: string | null = null;

  private apiClient: ApiClient | null = null;
  private snapshotStore: SnapshotStore | null = null;
  private snapshotListener: SnapshotListener = (): void => {
    this.refreshFromSnapshot();
  };
  private generation: number = 0;
  private readonly changeListeners: (() => void)[] = [];

  attach(client: ApiClient | null, snapshotStore: SnapshotStore | null): void {
    this.apiClient = client;
    if (this.snapshotStore !== null) {
      this.snapshotStore.removeListener(this.snapshotListener);
    }
    this.snapshotStore = snapshotStore;
    if (snapshotStore !== null) {
      snapshotStore.addListener(this.snapshotListener);
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

  detach(): void {
    this.apiClient = null;
    if (this.snapshotStore !== null) {
      this.snapshotStore.removeListener(this.snapshotListener);
      this.snapshotStore = null;
    }
    this.generation++;
    this.status = CachePageStatus.IDLE;
    this.items = [];
    this.capacity = null;
    this.nextCursor = null;
    this.loadingMore = false;
    this.actionJobId = null;
    this.actionError = null;
    this.errorMessage = null;
  }

  /** 首载/刷新（snapshot 变化也走这里）。 */
  refresh(): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = ++this.generation;
    this.status = CachePageStatus.LOADING;
    this.errorMessage = null;
    this.notifyChanged();
    client.listCacheJobs([], null).then((page: CacheJobPage) => {
      if (gen !== this.generation) {
        return;
      }
      this.items = page.items;
      this.capacity = page.capacity;
      this.nextCursor = page.nextCursor;
      this.status = CachePageStatus.READY;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.status = CachePageStatus.FAILED;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  loadMore(): void {
    const client = this.apiClient;
    if (client === null || this.loadingMore || this.nextCursor === null) {
      return;
    }
    if (this.status !== CachePageStatus.READY) {
      return;
    }
    const gen = this.generation;
    const cursor = this.nextCursor;
    this.loadingMore = true;
    this.notifyChanged();
    client.listCacheJobs([], cursor).then((page: CacheJobPage) => {
      if (gen !== this.generation) {
        return;
      }
      const merged = this.items.slice();
      for (const job of page.items) {
        if (!merged.some((existing) => existing.id === job.id)) {
          merged.push(job);
        }
      }
      this.items = merged;
      this.nextCursor = page.nextCursor;
      this.loadingMore = false;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.loadingMore = false;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** 取消：页面已二次确认；202 响应替换列表项。 */
  cancelJob(cacheJobId: string): void {
    this.performAction(cacheJobId, 'cancel');
  }

  /** 清理：202 响应替换列表项。 */
  cleanupJob(cacheJobId: string): void {
    this.performAction(cacheJobId, 'cleanup');
  }

  private performAction(cacheJobId: string, kind: string): void {
    const client = this.apiClient;
    if (client === null || this.actionJobId !== null) {
      return;
    }
    const gen = this.generation;
    this.actionJobId = cacheJobId;
    this.actionError = null;
    this.errorMessage = null;
    this.notifyChanged();
    const promise = kind === 'cancel'
      ? client.cancelCacheJob(cacheJobId)
      : client.cleanupCacheJob(cacheJobId);
    promise.then((job: CacheJobDetail) => {
      if (gen !== this.generation) {
        return;
      }
      this.replaceItem(job);
      this.actionJobId = null;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.actionJobId = null;
      this.actionError = this.errorCodeOf(err);
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  private replaceItem(job: CacheJobDetail): void {
    const index = this.items.findIndex((existing) => existing.id === job.id);
    const next = this.items.slice();
    if (index >= 0) {
      next[index] = job;
    } else {
      next.unshift(job);
    }
    this.items = next;
  }

  private refreshFromSnapshot(): void {
    // 快照更新触发当前列表刷新（保留分页真相由列表 API 保证）
    if (this.status !== CachePageStatus.READY && this.status !== CachePageStatus.FAILED) {
      return;
    }
    this.refresh();
  }

  /** 取消按钮显示条件。 */
  static canCancel(job: CacheJobDetail): boolean {
    const cancellable: string[] = ['queued', 'submitting', 'offlining', 'submit_uncertain', 'resolving'];
    return cancellable.includes(job.status);
  }

  /** 清理按钮显示条件。 */
  static canCleanup(job: CacheJobDetail): boolean {
    const cleanable: string[] = ['awaiting_selection', 'ready', 'cleanup_failed'];
    return cleanable.includes(job.status);
  }

  /** 任务操作中（cancelling/cleaning 不提供重复操作）。 */
  static isBusy(job: CacheJobDetail): boolean {
    return job.status === 'cancelling' || job.status === 'cleaning';
  }

  /** 13 状态中文文案。 */
  static statusText(status: string): string {
    const labels: Record<string, string> = {
      'queued': '排队中',
      'submitting': '正在提交',
      'offlining': '离线中',
      'submit_uncertain': '提交待确认',
      'resolving': '解析文件',
      'awaiting_selection': '待选文件',
      'ready': '可播放',
      'cancelling': '正在取消',
      'cleaning': '正在清理',
      'cleanup_failed': '清理失败',
      'failed': '任务失败',
      'cleaned': '已清理',
      'detached': '已失联',
    };
    return labels[status] ?? status;
  }

  private errorCodeOf(err: Error): string {
    if (err instanceof ApiException) {
      return err.code;
    }
    return 'client_transport_error';
  }

  private errorTextOf(err: Error): string {
    const code = this.errorCodeOf(err);
    if (code === 'cache_active_lease') {
      return '缓存正在播放，暂时不能清理';
    }
    if (code === 'cache_ownership_mismatch') {
      return '缓存目录归属不一致，任务已失联';
    }
    if (code === 'client_transport_error') {
      return '无法连接服务器，请稍后重试';
    }
    return '操作失败，请重试';
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}
