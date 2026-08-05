/**
 * 媒体库状态（AC-063/064/067/068/077）。
 *
 * - 六分类可组合（服务端 OR）、四标签叠加（服务端 AND）、来源/可播放/大小/收藏。
 * - 默认 publish_date_desc（null 最后，movie_id 决胜，由服务端保证）。
 * - 游标分页：generation 丢弃迟到响应；追加失败保留游标可重试；
 *   cursor 失效（validation_failed）清游标重载第一页（同 generation 仅一次）。
 * - 列表项身份用 movie ID（DoR：不用 index 作 key）。
 */

import { ApiClient, MovieListParams } from '../../core/api/ApiClient';
import { ApiException } from '../../core/api/ApiModels';
import { MovieSummary } from '../../core/api/ApiModels';

export enum LibraryStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
  INVALID,
  APPENDING,
  APPEND_FAILED,
}

export class LibraryFilters {
  static readonly CATEGORIES: string[] = ['亚洲有码', '亚洲无码', '中文字幕', '4K原版', '素人有码', 'FC2'];
  static readonly LABELS: string[] = ['subtitle', 'cracked', '4k', 'censored'];
  static readonly SORTS: string[] = ['publish_date_desc', 'publish_date_asc', 'number_asc'];
  static readonly PAGE_SIZE = 24;
}

@ObservedV2
export class LibraryStore {
  // ---- 筛选状态（仅内存，契约：页面级状态） ----
  @Trace categories: string[] = [];
  @Trace labels: string[] = [];
  @Trace sourceWebsite: string | null = null;
  @Trace playable: boolean | null = null;
  @Trace minSizeMb: number | null = null;
  @Trace maxSizeMb: number | null = null;
  @Trace favorite: boolean = false;
  @Trace sort: string = 'publish_date_desc';

  // ---- 数据状态 ----
  @Trace status: LibraryStatus = LibraryStatus.IDLE;
  @Trace items: MovieSummary[] = [];
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

  detach(): void {
    this.apiClient = null;
    // 会话切换时重置数据状态（保留筛选偏好），避免下次进入显示过期列表
    this.generation++;
    this.items = [];
    this.nextCursor = null;
    this.status = LibraryStatus.IDLE;
    this.errorMessage = null;
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
    return this.status === LibraryStatus.LOADING || this.status === LibraryStatus.APPENDING;
  }

  // ---- 筛选操作 ----

  toggleCategory(category: string): void {
    this.categories = this.toggleIn(this.categories, category);
    this.refresh();
  }

  toggleLabel(label: string): void {
    this.labels = this.toggleIn(this.labels, label);
    this.refresh();
  }

  setSource(source: string | null): void {
    this.sourceWebsite = source;
    this.refresh();
  }

  setPlayable(playable: boolean | null): void {
    this.playable = playable;
    this.refresh();
  }

  setSizeRange(min: number | null, max: number | null): void {
    if (min !== null && max !== null && min > max) {
      this.status = LibraryStatus.INVALID;
      this.errorMessage = '最小资源大小不能大于最大资源大小';
      this.notifyChanged();
      return;
    }
    this.minSizeMb = min;
    this.maxSizeMb = max;
    this.refresh();
  }

  toggleFavorite(): void {
    this.setFavorite(!this.favorite);
  }

  /** 收藏筛选（含 UI 直赋路径，变更即刷新避免新筛选+旧游标混搭）。 */
  setFavorite(value: boolean): void {
    this.favorite = value;
    this.refresh();
  }

  setSort(sort: string): void {
    if (LibraryFilters.SORTS.includes(sort)) {
      this.sort = sort;
      this.refresh();
    }
  }

  resetFilters(): void {
    this.categories = [];
    this.labels = [];
    this.sourceWebsite = null;
    this.playable = null;
    this.minSizeMb = null;
    this.maxSizeMb = null;
    this.favorite = false;
    this.sort = 'publish_date_desc';
    this.refresh();
  }

  // ---- 分页 ----

  /** 刷新第一页（筛选变更后调用）。 */
  refresh(): void {
    if (this.apiClient === null) {
      return;
    }
    this.generation++;
    this.nextCursor = null;
    this.status = LibraryStatus.LOADING;
    this.errorMessage = null;
    this.notifyChanged();
    this.requestFirstPage(this.generation);
  }

  /** 加载下一页（滚动到底时调用）。 */
  loadMore(): void {
    if (this.apiClient === null || this.appending) {
      return;
    }
    if (this.status !== LibraryStatus.READY && this.status !== LibraryStatus.APPEND_FAILED) {
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

  private async requestFirstPage(gen: number): Promise<void> {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    try {
      const page = await client.listMovies(this.buildParams(null));
      if (gen !== this.generation) {
        return;
      }
      this.items = page.items;
      this.nextCursor = page.nextCursor;
      this.status = LibraryStatus.READY;
      this.errorMessage = null;
      this.notifyChanged();
    } catch (err) {
      if (gen !== this.generation) {
        return;
      }
      this.status = LibraryStatus.FAILED;
      this.errorMessage = err instanceof Error ? err.message : '媒体库加载失败';
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
    this.status = LibraryStatus.APPENDING;
    try {
      const page = await client.listMovies(this.buildParams(cursor));
      if (gen !== this.generation) {
        return;
      }
      const merged = this.items.slice();
      for (const item of page.items) {
        if (!merged.some((existing) => existing.id === item.id)) {
          merged.push(item);
        }
      }
      this.items = merged;
      this.nextCursor = page.nextCursor;
      this.status = LibraryStatus.READY;
      this.errorMessage = null;
      this.notifyChanged();
    } catch (err) {
      if (gen !== this.generation) {
        return;
      }
      // 游标失效（422 validation_failed）：清游标重载第一页（同 generation 只恢复一次）
      if (this.isCursorInvalidation(err) && this.cursorRecoveredGeneration !== gen) {
        this.cursorRecoveredGeneration = gen;
        this.nextCursor = null;
        this.status = LibraryStatus.LOADING;
        this.errorMessage = null;
        this.notifyChanged();
        this.requestFirstPage(gen);
        return;
      }
      this.status = LibraryStatus.APPEND_FAILED;
      this.errorMessage = err instanceof Error ? err.message : '加载更多失败';
      this.notifyChanged();
    } finally {
      this.appending = false;
    }
  }

  private isCursorInvalidation(err: Error): boolean {
    const code = (err as ApiException).code;
    if (code === 'validation_failed') {
      return true;
    }
    // 兜底：HTTP 422 也视为游标失效
    return err.message.includes('422');
  }

  private buildParams(cursor: string | null): MovieListParams {
    const params: MovieListParams = {
      cursor: cursor,
      limit: LibraryFilters.PAGE_SIZE,
      categories: this.categories.length > 0 ? this.categories.slice() : undefined,
      labels: this.labels.length > 0 ? this.labels.slice() : undefined,
      sourceWebsite: this.sourceWebsite,
      playable: this.playable,
      minResourceSizeMb: this.minSizeMb,
      maxResourceSizeMb: this.maxSizeMb,
      sort: this.sort,
      favorite: this.favorite ? true : undefined,
    };
    return params;
  }

  private toggleIn(list: string[], value: string): string[] {
    if (list.includes(value)) {
      return list.filter((item) => item !== value);
    }
    return list.slice().concat([value]);
  }
}

/** 全局媒体库单例。 */
export const libraryStore = new LibraryStore();
