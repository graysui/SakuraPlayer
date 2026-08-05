/**
 * 女优列表与详情状态（AC-051/052/053/075/076/077）。
 *
 * - 姓名/权威别名搜索（300ms 防抖，Enter 立即提交），普通/收藏（favorite=true）模式。
 * - 切换查询/模式 generation 竞态并清空旧内容；刷新在途保留现有内容，失败保留
 *   items/cursor（非阻断重试）；追加失败保留 items/cursor 局部重试；刷新期禁止追加。
 * - cursor validation_failed 按当前 scope 重载第一页（同 generation 一次）。
 * - 收藏在途防重；成功后同步已加载列表项；收藏模式取消收藏移除该项但不伪造下一页；
 *   失败保留旧值并显示错误。详情页通过 acceptFavorite 与列表双向同步。
 * - 会话变化（detach）清空全部状态（含查询与模式）。
 */

import { ApiClient, ActorListParams } from '../../core/api/ApiClient';
import { ActorDetail, ActorSummary, ApiException } from '../../core/api/ApiModels';

export enum ActorsStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
  APPENDING,
  APPEND_FAILED,
}

@ObservedV2
export class ActorsStore {
  static readonly PAGE_SIZE = 24;
  static readonly DEBOUNCE_MS = 300;

  @Trace query: string = '';
  @Trace activeQuery: string = '';
  @Trace favoriteMode: boolean = false;
  @Trace status: ActorsStatus = ActorsStatus.IDLE;
  @Trace items: ActorSummary[] = [];
  @Trace refreshing: boolean = false;
  @Trace errorMessage: string | null = null;
  @Trace favoriteInFlight: string[] = [];
  @Trace favoriteErrorMessage: string | null = null;

  private apiClient: ApiClient | null = null;
  private generation: number = 0;
  private nextCursor: string | null = null;
  private appending: boolean = false;
  private cursorRecoveredGeneration: number = -1;
  private debounceTimer: number = -1;
  private readonly changeListeners: (() => void)[] = [];

  attach(apiClient: ApiClient | null): void {
    this.apiClient = apiClient;
  }

  /** 会话切换时清空全部状态（含查询与模式），避免下次进入显示过期列表。 */
  detach(): void {
    this.apiClient = null;
    if (this.debounceTimer >= 0) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = -1;
    }
    this.generation++;
    this.query = '';
    this.activeQuery = '';
    this.favoriteMode = false;
    this.items = [];
    this.nextCursor = null;
    this.status = ActorsStatus.IDLE;
    this.refreshing = false;
    this.appending = false;
    this.cursorRecoveredGeneration = -1;
    this.errorMessage = null;
    this.favoriteInFlight = [];
    this.favoriteErrorMessage = null;
    this.notifyChanged();
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

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }

  get hasMore(): boolean {
    return this.nextCursor !== null;
  }

  get isLoading(): boolean {
    return this.status === ActorsStatus.LOADING || this.status === ActorsStatus.APPENDING;
  }

  isFavoriteInFlight(actorId: string): boolean {
    return this.favoriteInFlight.includes(actorId);
  }

  // ---- 查询与模式 ----

  /** 输入变更：重置 300ms 防抖。 */
  setQuery(query: string): void {
    this.query = query;
    if (this.debounceTimer >= 0) {
      clearTimeout(this.debounceTimer);
    }
    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = -1;
      this.commitQuery();
    }, ActorsStore.DEBOUNCE_MS);
    this.notifyChanged();
  }

  /** 页面销毁时取消待提交查询（避免导航离开后仍发起请求）。 */
  cancelPendingQuery(): void {
    if (this.debounceTimer >= 0) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = -1;
    }
  }

  /** Enter 立即提交当前查询。 */
  submitQuery(): void {
    if (this.debounceTimer >= 0) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = -1;
    }
    this.commitQuery();
  }

  private commitQuery(): void {
    const normalized = this.query.trim();
    if (normalized === this.activeQuery && this.status !== ActorsStatus.IDLE) {
      return;
    }
    this.activeQuery = normalized;
    this.requestFirstPage();
  }

  toggleFavoriteMode(): void {
    this.favoriteMode = !this.favoriteMode;
    this.requestFirstPage();
  }

  // ---- 加载 ----

  refresh(): void {
    if (this.status === ActorsStatus.READY || this.status === ActorsStatus.APPEND_FAILED ||
      this.status === ActorsStatus.APPENDING) {
      this.refreshKeepContent();
    } else {
      this.requestFirstPage();
    }
  }

  retryInitial(): void {
    this.requestFirstPage();
  }

  /** 加载下一页（滚动到底时调用）。刷新在途禁止追加；APPEND_FAILED 只允许显式重试。 */
  loadMore(): void {
    if (this.apiClient === null || this.appending) {
      return;
    }
    if (this.refreshing) {
      return;
    }
    if (this.status === ActorsStatus.APPEND_FAILED) {
      return;
    }
    if (this.status !== ActorsStatus.READY) {
      return;
    }
    if (this.nextCursor === null) {
      return;
    }
    this.appendPage();
  }

  retryAppend(): void {
    this.appendPage();
  }

  // ---- 收藏 ----

  /** 列表项收藏切换：在途防重；成功后同步列表；favorite 模式取消收藏移除项。 */
  setFavorite(actorId: string, enabled: boolean): void {
    const client = this.apiClient;
    if (client === null || this.favoriteInFlight.includes(actorId)) {
      return;
    }
    const gen = this.generation;
    const inFlight = this.favoriteInFlight.slice();
    inFlight.push(actorId);
    this.favoriteInFlight = inFlight;
    this.favoriteErrorMessage = null;
    this.notifyChanged();
    client.setActorFavorite(actorId, enabled).then(() => {
      // 收藏在途期间切换 scope：不污染新列表
      if (gen !== this.generation) {
        return;
      }
      this.favoriteInFlight = this.favoriteInFlight.filter((id: string) => id !== actorId);
      this.applyFavoriteResult(actorId, enabled);
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.favoriteInFlight = this.favoriteInFlight.filter((id: string) => id !== actorId);
      this.favoriteErrorMessage = err instanceof Error ? err.message : '收藏操作失败';
      this.notifyChanged();
    });
  }

  /** 详情页收藏变化同步到列表（收藏模式取消收藏时移除项）。 */
  acceptFavorite(actorId: string, enabled: boolean): void {
    this.applyFavoriteResult(actorId, enabled);
    this.notifyChanged();
  }

  private applyFavoriteResult(actorId: string, enabled: boolean): void {
    const items = this.items.slice();
    const index = items.findIndex((item: ActorSummary) => item.id === actorId);
    if (index < 0) {
      return;
    }
    if (this.favoriteMode && !enabled) {
      items.splice(index, 1);
    } else {
      items[index] = ActorsStore.withFavorite(items[index], enabled);
    }
    this.items = items;
  }

  // ---- 内部 ----

  private requestFirstPage(): void {
    if (this.apiClient === null) {
      return;
    }
    ++this.generation;
    this.cursorRecoveredGeneration = -1;
    this.nextCursor = null;
    this.items = [];
    this.favoriteInFlight = [];
    this.status = ActorsStatus.LOADING;
    this.refreshing = false;
    this.errorMessage = null;
    this.favoriteErrorMessage = null;
    this.notifyChanged();
    this.fetchFirstPage(false).catch(() => {
    });
  }

  private refreshKeepContent(): void {
    if (this.apiClient === null) {
      return;
    }
    ++this.generation;
    this.cursorRecoveredGeneration = -1;
    this.favoriteInFlight = [];
    this.refreshing = true;
    this.errorMessage = null;
    this.notifyChanged();
    this.fetchFirstPage(true).catch(() => {
    });
  }

  private async fetchFirstPage(keepContent: boolean): Promise<void> {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = this.generation;
    try {
      const page = await client.listActors(this.buildParams(null));
      if (gen !== this.generation) {
        return;
      }
      this.items = page.items;
      this.nextCursor = page.nextCursor;
      this.refreshing = false;
      this.errorMessage = null;
      this.status = ActorsStatus.READY;
      this.notifyChanged();
    } catch (err) {
      if (gen !== this.generation) {
        return;
      }
      this.refreshing = false;
      if (keepContent) {
        this.status = ActorsStatus.READY;
        this.errorMessage = err instanceof Error ? err.message : '刷新失败';
        this.notifyChanged();
        return;
      }
      this.status = ActorsStatus.FAILED;
      this.errorMessage = err instanceof Error ? err.message : '女优列表加载失败';
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
    this.status = ActorsStatus.APPENDING;
    this.errorMessage = null;
    this.notifyChanged();
    try {
      const page = await client.listActors(this.buildParams(cursor));
      if (gen !== this.generation) {
        return;
      }
      const merged = this.items.slice();
      for (const item of page.items) {
        merged.push(item);
      }
      this.items = merged;
      this.nextCursor = page.nextCursor;
      this.status = ActorsStatus.READY;
      this.errorMessage = null;
      this.notifyChanged();
    } catch (err) {
      if (gen !== this.generation) {
        return;
      }
      if (this.isCursorInvalidation(err) && this.cursorRecoveredGeneration !== gen) {
        this.cursorRecoveredGeneration = gen;
        this.status = ActorsStatus.READY;
        this.refreshKeepContent();
        return;
      }
      this.status = ActorsStatus.APPEND_FAILED;
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

  private buildParams(cursor: string | null): ActorListParams {
    return {
      query: this.activeQuery,
      cursor: cursor,
      limit: ActorsStore.PAGE_SIZE,
      favorite: this.favoriteMode,
    };
  }

  private static withFavorite(summary: ActorSummary, favorite: boolean): ActorSummary {
    return new ActorSummary(summary.id, summary.displayName, summary.nameJa, summary.nameZh,
      summary.aliases, summary.profileUrl, favorite);
  }
}

/** 全局女优列表单例。 */
export const actorsStore = new ActorsStore();

// ---- 详情 ----

export enum ActorDetailStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
}

/** 女优详情状态（页面级实例；收藏通过构造回调与列表双向同步）。 */
@ObservedV2
export class ActorDetailStore {
  @Trace status: ActorDetailStatus = ActorDetailStatus.IDLE;
  @Trace detail: ActorDetail | null = null;
  @Trace errorMessage: string | null = null;
  @Trace favoriteInFlight: boolean = false;
  @Trace favoriteErrorMessage: string | null = null;

  private readonly onFavoriteSynced: (actorId: string, enabled: boolean) => void;
  private apiClient: ApiClient | null = null;
  private generation: number = 0;
  private actorId: string | null = null;
  private pendingFavorite: boolean | null = null;
  private readonly changeListeners: (() => void)[] = [];

  /** onFavoriteSynced：收藏成功后同步已加载列表（页面传入 actorsStore.acceptFavorite）。 */
  constructor(onFavoriteSynced: (actorId: string, enabled: boolean) => void = (actorId: string, enabled: boolean) => {
  }) {
    this.onFavoriteSynced = onFavoriteSynced;
  }

  attach(apiClient: ApiClient | null): void {
    this.apiClient = apiClient;
  }

  detach(): void {
    this.apiClient = null;
    this.generation++;
    this.actorId = null;
    this.detail = null;
    this.status = ActorDetailStatus.IDLE;
    this.errorMessage = null;
    this.favoriteInFlight = false;
    this.favoriteErrorMessage = null;
    this.notifyChanged();
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

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }

  load(actorId: string): void {
    this.actorId = actorId;
    this.requestDetail();
  }

  retry(): void {
    this.requestDetail();
  }

  private requestDetail(): void {
    const client = this.apiClient;
    const actorId = this.actorId;
    if (client === null || actorId === null) {
      return;
    }
    const gen = ++this.generation;
    this.status = ActorDetailStatus.LOADING;
    this.errorMessage = null;
    this.favoriteInFlight = false;
    this.favoriteErrorMessage = null;
    this.notifyChanged();
    client.getActor(actorId).then((detail: ActorDetail) => {
      if (gen !== this.generation) {
        return;
      }
      this.detail = detail;
      this.status = ActorDetailStatus.READY;
      // LOADING 期间完成的收藏：合并到服务端详情（避免被覆盖）
      if (this.pendingFavorite !== null) {
        this.applyFavorite(this.pendingFavorite);
        this.pendingFavorite = null;
      }
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.status = ActorDetailStatus.FAILED;
      this.errorMessage = err instanceof Error ? err.message : '详情加载失败';
      this.notifyChanged();
    });
  }

  /** 收藏切换：在途防重；成功后更新详情并同步列表。 */
  setFavorite(enabled: boolean): void {
    const client = this.apiClient;
    const actorId = this.actorId;
    if (client === null || actorId === null || this.favoriteInFlight) {
      return;
    }
    const gen = this.generation;
    this.favoriteInFlight = true;
    this.favoriteErrorMessage = null;
    this.notifyChanged();
    client.setActorFavorite(actorId, enabled).then(() => {
      if (gen !== this.generation) {
        this.favoriteInFlight = false;
        this.notifyChanged();
        return;
      }
      this.favoriteInFlight = false;
      if (this.detail === null) {
        // 详情尚未加载完成：记录待合并，避免被服务端旧值覆盖
        this.pendingFavorite = enabled;
      } else {
        this.applyFavorite(enabled);
      }
      this.onFavoriteSynced(actorId, enabled);
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.favoriteInFlight = false;
      this.favoriteErrorMessage = err instanceof Error ? err.message : '收藏操作失败';
      this.notifyChanged();
    });
  }

  /** 列表收藏变化同步到当前详情。 */
  acceptFavorite(enabled: boolean): void {
    this.applyFavorite(enabled);
    this.notifyChanged();
  }

  private applyFavorite(enabled: boolean): void {
    const detail = this.detail;
    if (detail === null) {
      return;
    }
    const summary = detail.summary;
    const updated = new ActorSummary(summary.id, summary.displayName, summary.nameJa, summary.nameZh,
      summary.aliases, summary.profileUrl, enabled);
    this.detail = new ActorDetail(updated, detail.bio, detail.bioOriginal, detail.galleryUrls, detail.movies);
  }
}
