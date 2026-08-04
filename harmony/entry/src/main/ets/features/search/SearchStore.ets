/**
 * 全局搜索状态（AC-065/AC-066）。
 *
 * - 300ms 防抖；generation 防过期竞态。
 * - 结果按 影片/女优/元数据补全 三分组（后端已按番号精确置顶排序）。
 * - pending 状态：queued 等待补全 / running 正在补全 / failed 补全失败。
 * - 监听事件快照：catalog core_ready 变化后自动重查，pending 移入影片组。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ActorSummary, MovieSummary, PendingMetadata } from '../../core/api/ApiModels';
import { SnapshotListener, SnapshotStore } from '../../core/events/SnapshotStore';

export enum SearchStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
}

const DEBOUNCE_MS = 300;

@ObservedV2
export class SearchStore {
  @Trace query: string = '';
  @Trace status: SearchStatus = SearchStatus.IDLE;
  @Trace movies: MovieSummary[] = [];
  @Trace actors: ActorSummary[] = [];
  @Trace pending: PendingMetadata[] = [];
  @Trace errorCode: string | null = null;
  @Trace isRefreshing: boolean = false;

  private apiClient: ApiClient | null = null;
  private snapshot: SnapshotStore | null = null;
  private generation: number = 0;
  private debounceTimer: number | null = null;
  private readonly snapshotListener: SnapshotListener;

  constructor() {
    this.snapshotListener = (): void => this.onSnapshotChanged();
  }

  /** 绑定认证客户端与事件快照（AuthStore 认证成功后调用；可为 null）。 */
  attach(apiClient: ApiClient | null, snapshot: SnapshotStore | null): void {
    this.apiClient = apiClient;
    this.snapshot = snapshot;
    if (snapshot !== null) {
      snapshot.addListener(this.snapshotListener);
    }
  }

  /** 注销快照监听（会话退出时调用）。 */
  detach(): void {
    if (this.snapshot !== null) {
      this.snapshot.removeListener(this.snapshotListener);
      this.snapshot = null;
    }
    this.apiClient = null;
  }

  /** 输入更新：300ms 防抖后搜索；空输入回到 idle。 */
  updateQuery(value: string): void {
    this.query = value;
    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }
    if (value.trim().length === 0) {
      this.generation++;
      this.status = SearchStatus.IDLE;
      this.movies = [];
      this.actors = [];
      this.pending = [];
      this.errorCode = null;
      return;
    }
    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null;
      this.runSearch(value.trim(), false);
    }, DEBOUNCE_MS);
  }

  /** 手动刷新：保留现有结果静默重查（补全完成后调用）。 */
  refresh(): void {
    if (this.query.trim().length > 0) {
      this.runSearch(this.query.trim(), true);
    }
  }

  /** 清空搜索状态。 */
  clear(): void {
    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }
    this.generation++;
    this.query = '';
    this.status = SearchStatus.IDLE;
    this.movies = [];
    this.actors = [];
    this.pending = [];
    this.errorCode = null;
  }

  private async runSearch(query: string, preserve: boolean): Promise<void> {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = ++this.generation;
    this.status = SearchStatus.LOADING;
    if (preserve) {
      this.isRefreshing = true;
    }
    try {
      const result = await client.search(query, 24);
      if (gen !== this.generation) {
        return; // 过期竞态
      }
      this.movies = result.movies;
      this.actors = result.actors;
      this.pending = result.pendingMetadata;
      this.status = SearchStatus.READY;
      this.errorCode = null;
    } catch (err) {
      if (gen !== this.generation) {
        return;
      }
      this.status = SearchStatus.FAILED;
      this.errorCode = err instanceof Error ? err.message : '搜索失败';
      if (!preserve) {
        this.movies = [];
        this.actors = [];
        this.pending = [];
      }
    } finally {
      this.isRefreshing = false;
    }
  }

  /** 快照变化（catalog core_ready 等触发 recover）：有待补全项时自动重查。 */
  private onSnapshotChanged(): void {
    if (this.query.trim().length > 0 && this.pending.length > 0 && this.apiClient !== null) {
      this.runSearch(this.query.trim(), true);
    }
  }
}

/** 全局搜索单例。 */
export const searchStore = new SearchStore();
