/**
 * 排行榜状态（AC-046/069-073）。
 *
 * - 只读后端本地不可变快照；打开/刷新页面不触发客户端 JavDB 抓取（AC-069）。
 * - 四榜单（日/周/月/TOP250）；TOP250 支持总榜 + 服务端 available_years 年度（AC-070）。
 * - 切换 board 清空 year；year 只在服务端声明适用（top250 且 available_years 内）时可选。
 * - generation 竞态：切换/刷新丢弃迟到响应；刷新在途保留现有内容，失败保留
 *   items/cursor/synced_at（可重试提示）；追加失败保留 items/cursor 局部重试。
 * - cursor 失效（validation_failed）按当前 board/year 重载第一页（同 generation 一次）。
 * - 503 ranking_snapshot_unavailable 且 reason 在固定集合内 → UNAVAILABLE；
 *   未知 reason/其他错误 → FAILED，不猜测凭据状态（AC-046/073）。
 */

import { ApiClient, RankingQueryParams } from '../../core/api/ApiClient';
import { ApiException, RankingItem, RankingPage } from '../../core/api/ApiModels';

export enum RankingsStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
  UNAVAILABLE,
  APPENDING,
  APPEND_FAILED,
}

@ObservedV2
export class RankingsStore {
  /** 榜单枚举单一来源（与 DTO 校验一致）。 */
  static readonly BOARDS: string[] = RankingPage.BOARDS.slice();
  static readonly PAGE_SIZE = 24;
  static readonly UNAVAILABLE_REASONS: string[] = [
    'credentials_not_configured', 'credentials_invalid', 'never_synced', 'sync_failed',
  ];

  @Trace board: string = 'daily';
  @Trace year: number | null = null;
  @Trace status: RankingsStatus = RankingsStatus.IDLE;
  @Trace items: RankingItem[] = [];
  @Trace availableYears: number[] = [];
  @Trace syncedAt: string | null = null;
  @Trace unavailableReason: string | null = null;
  @Trace refreshing: boolean = false;
  @Trace errorMessage: string | null = null;

  private apiClient: ApiClient | null = null;
  private generation: number = 0;
  private nextCursor: string | null = null;
  private appending: boolean = false;
  private cursorRecoveredGeneration: number = -1;
  private readonly changeListeners: (() => void)[] = [];

  attach(apiClient: ApiClient | null): void {
    this.apiClient = apiClient;
  }

  /** 会话切换时清空全部状态（含选择），避免下次进入显示过期榜单。 */
  detach(): void {
    this.apiClient = null;
    this.generation++;
    this.board = 'daily';
    this.year = null;
    this.items = [];
    this.nextCursor = null;
    this.availableYears = [];
    this.syncedAt = null;
    this.unavailableReason = null;
    this.refreshing = false;
    this.appending = false;
    this.errorMessage = null;
    this.status = RankingsStatus.IDLE;
    this.notifyChanged();
  }

  /** 数据/状态变化监听（页面 DataSource 同步用；命名回调可注销）。 */
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

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }

  get hasMore(): boolean {
    return this.nextCursor !== null;
  }

  get isLoading(): boolean {
    return this.status === RankingsStatus.LOADING || this.status === RankingsStatus.APPENDING;
  }

  // ---- 选择 ----

  /** 选择榜单：切换清空 year 与年度选项；同 board 且已有状态时幂等。 */
  selectBoard(board: string): void {
    if (!RankingsStore.BOARDS.includes(board)) {
      return;
    }
    if (board === this.board && this.status !== RankingsStatus.IDLE) {
      return;
    }
    this.board = board;
    this.year = null;
    this.availableYears = [];
    this.requestFirstPage();
  }

  /** 选择 TOP250 年份：总榜传 null；仅服务端 available_years 内可选。 */
  selectYear(year: number | null): void {
    if (this.board !== 'top250') {
      return;
    }
    if (year !== null && !this.availableYears.includes(year)) {
      return;
    }
    if (year === this.year && this.status !== RankingsStatus.IDLE) {
      return;
    }
    this.year = year;
    this.requestFirstPage();
  }

  // ---- 加载 ----

  /** 下拉刷新：已有成功快照保留现有内容；否则等同首载。 */
  refresh(): void {
    if (this.status === RankingsStatus.READY || this.status === RankingsStatus.APPEND_FAILED ||
      this.status === RankingsStatus.APPENDING) {
      this.refreshKeepContent();
    } else {
      this.requestFirstPage();
    }
  }

  /** 失败/不可用后重试首载。 */
  retryInitial(): void {
    this.requestFirstPage();
  }

  /** 加载下一页（滚动到底时调用）。刷新在途禁止追加，避免旧 cursor 与新快照混叠。 */
  loadMore(): void {
    if (this.apiClient === null || this.appending) {
      return;
    }
    if (this.refreshing) {
      return;
    }
    if (this.status !== RankingsStatus.READY && this.status !== RankingsStatus.APPEND_FAILED) {
      return;
    }
    if (this.nextCursor === null) {
      return;
    }
    this.appendPage();
  }

  /** 追加失败后重试（同 cursor）。 */
  retryAppend(): void {
    this.appendPage();
  }

  // ---- 内部 ----

  private requestFirstPage(): void {
    if (this.apiClient === null) {
      return;
    }
    ++this.generation;
    this.cursorRecoveredGeneration = -1;
    this.nextCursor = null;
    // 切换 board/year 清空旧榜单内容：加载/失败期间不得显示其他 scope 旧数据
    this.items = [];
    this.status = RankingsStatus.LOADING;
    this.syncedAt = null;
    this.unavailableReason = null;
    this.refreshing = false;
    this.errorMessage = null;
    this.notifyChanged();
    this.fetchFirstPage(false).catch(() => {
    });
  }

  /** 刷新/游标恢复：保留 items/cursor/synced_at，成功时整体替换。 */
  private refreshKeepContent(): void {
    if (this.apiClient === null) {
      return;
    }
    ++this.generation;
    this.cursorRecoveredGeneration = -1;
    this.refreshing = true;
    this.errorMessage = null;
    this.notifyChanged();
    this.fetchFirstPage(true).catch(() => {
    });
  }

  /**
   * 请求第一页。keepContent=true 时（刷新/游标恢复）保留既有 items 与 cursor，
   * 失败只设置 errorMessage（status 保持 READY）；否则为全新加载。
   */
  private async fetchFirstPage(keepContent: boolean): Promise<void> {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = this.generation;
    try {
      const page = await client.getRanking(this.buildParams(null));
      if (gen !== this.generation) {
        return;
      }
      this.items = page.items;
      this.nextCursor = page.nextCursor;
      this.syncedAt = page.syncedAt;
      if (page.board === 'top250') {
        this.availableYears = page.availableYears;
        // 刷新后服务端不再声明当前 year：回落总榜，避免 Select 显示陈旧年份
        if (this.year !== null && !page.availableYears.includes(this.year)) {
          this.year = null;
        }
      } else {
        this.availableYears = [];
      }
      this.unavailableReason = null;
      this.refreshing = false;
      this.errorMessage = null;
      this.status = RankingsStatus.READY;
      this.notifyChanged();
    } catch (err) {
      if (gen !== this.generation) {
        return;
      }
      this.refreshing = false;
      if (keepContent) {
        // 刷新失败保留现有 items/cursor/synced_at（可重试提示）
        this.status = RankingsStatus.READY;
        this.errorMessage = err instanceof Error ? err.message : '刷新失败';
        this.notifyChanged();
        return;
      }
      const reason = this.unavailableReasonFrom(err);
      if (reason !== null) {
        this.status = RankingsStatus.UNAVAILABLE;
        this.unavailableReason = reason;
      } else {
        this.status = RankingsStatus.FAILED;
      }
      this.errorMessage = err instanceof Error ? err.message : '排行榜加载失败';
      this.notifyChanged();
    }
  }

  private async appendPage(): Promise<void> {
    if (this.appending) {
      return;
    }
    const client = this.apiClient;
    if (client === null || this.nextCursor === null) {
      return;
    }
    this.appending = true;
    const gen = this.generation;
    const cursor = this.nextCursor;
    this.status = RankingsStatus.APPENDING;
    this.errorMessage = null;
    this.notifyChanged();
    try {
      const page = await client.getRanking(this.buildParams(cursor));
      if (gen !== this.generation) {
        return;
      }
      // 追加保持 rank/影片顺序（不按本地 rank/影片重新排序、不去重）
      const merged = this.items.slice();
      for (const item of page.items) {
        merged.push(item);
      }
      this.items = merged;
      this.nextCursor = page.nextCursor;
      this.status = RankingsStatus.READY;
      this.errorMessage = null;
      this.notifyChanged();
    } catch (err) {
      if (gen !== this.generation) {
        return;
      }
      if (this.isCursorInvalidation(err) && this.cursorRecoveredGeneration !== gen) {
        // cursor 失效：清游标并按当前 board/year 重载第一页（同 generation 一次）
        this.cursorRecoveredGeneration = gen;
        this.refreshKeepContent();
        return;
      }
      this.status = RankingsStatus.APPEND_FAILED;
      this.errorMessage = err instanceof Error ? err.message : '加载更多失败';
      this.notifyChanged();
    } finally {
      this.appending = false;
    }
  }

  private isCursorInvalidation(err: Error): boolean {
    if (!(err instanceof ApiException)) {
      return false;
    }
    return err.code === 'validation_failed' || err.statusCode === 422;
  }

  /** 仅当 503 + ranking_snapshot_unavailable + 固定 reason 才返回 reason，否则 null。 */
  private unavailableReasonFrom(err: Error): string | null {
    if (!(err instanceof ApiException)) {
      return null;
    }
    if (err.code !== 'ranking_snapshot_unavailable' || err.statusCode !== 503) {
      return null;
    }
    const details = err.details;
    if (details === null || details === undefined) {
      return null;
    }
    try {
      const parsed = JSON.parse(details) as Record<string, Object>;
      const reason = parsed['reason'];
      if (typeof reason === 'string' && RankingsStore.UNAVAILABLE_REASONS.includes(reason)) {
        return reason;
      }
    } catch (e) {
      // 非法 details：不猜测凭据状态
    }
    return null;
  }

  private buildParams(cursor: string | null): RankingQueryParams {
    return {
      board: this.board,
      year: this.year,
      cursor: cursor,
      limit: RankingsStore.PAGE_SIZE,
    };
  }
}

/** 全局排行榜单例。 */
export const rankingsStore = new RankingsStore();
