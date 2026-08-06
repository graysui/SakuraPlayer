/**
 * 影片详情 Store（AC-031/033/034/035/068/074/077/078）。
 *
 * - 按 movie_id 加载聚合详情；generation 竞态丢弃迟到响应。
 * - 受限详情（metadata_state != core_ready）：不显示收藏、不调 favorite API；来源仍可选。
 * - 收藏在途防重：成功替换详情 favorite；失败保留旧值并显示非阻断错误。
 * - 来源选择：仅 ready 且来源存在且非 rejected 才可选；重载后来源消失自动清空；
 *   页面初始不选来源；rejected 不得输出 source_id。
 * - detach（认证/会话变化）清空全部状态，含来源选择。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, MovieDetail, ProtocolException } from '../../core/api/ApiModels';

export enum MovieDetailStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
}

@ObservedV2
export class MovieDetailStore {
  @Trace movieId: string | null = null;
  @Trace status: MovieDetailStatus = MovieDetailStatus.IDLE;
  @Trace detail: MovieDetail | null = null;
  @Trace errorCode: string | null = null;
  @Trace favoriteInFlight: boolean = false;
  @Trace favoriteError: string | null = null;
  @Trace selectedSourceId: string | null = null;

  private apiClient: ApiClient | null = null;
  private generation: number = 0;
  private readonly changeListeners: (() => void)[] = [];

  attach(client: ApiClient | null): void {
    this.apiClient = client;
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

  /** 认证服务端/会话变化：清空全部状态（含来源选择与收藏在途）。 */
  detach(): void {
    this.apiClient = null;
    this.generation++;
    this.movieId = null;
    this.status = MovieDetailStatus.IDLE;
    this.detail = null;
    this.errorCode = null;
    this.favoriteInFlight = false;
    this.favoriteError = null;
    this.selectedSourceId = null;
    this.notifyChanged();
  }

  isNotFound(): boolean {
    return this.errorCode === 'resource_not_found';
  }

  /** 按 MovieId 加载；切换 MovieId 清空旧详情与来源选择。 */
  load(movieId: string): void {
    const client = this.client();
    if (client === null) {
      return;
    }
    const previousSelection = this.movieId === movieId ? this.selectedSourceId : null;
    if (previousSelection === null) {
      // 切换影片：清空旧影片来源选择（契约：切换 MovieId 必须清空选择）
      this.selectedSourceId = null;
    }
    const gen = ++this.generation;
    this.movieId = movieId;
    this.status = MovieDetailStatus.LOADING;
    this.detail = null;
    this.errorCode = null;
    this.favoriteInFlight = false;
    this.favoriteError = null;
    this.notifyChanged();
    client.getMovie(movieId).then((detail: MovieDetail) => {
      if (gen !== this.generation) {
        return;
      }
      // 来源重查后失效自动清空选择
      if (previousSelection !== null && !this.sourceSelectable(detail, previousSelection)) {
        this.selectedSourceId = null;
      }
      this.detail = detail;
      this.status = MovieDetailStatus.READY;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.status = MovieDetailStatus.FAILED;
      this.errorCode = this.errorCodeOf(err);
      this.selectedSourceId = null;
      this.notifyChanged();
    });
  }

  /** 普通失败重试：只请求当前 MovieId。 */
  retry(): void {
    const movieId = this.movieId;
    if (movieId === null) {
      return;
    }
    this.load(movieId);
  }

  /** 收藏切换：受限详情/在途/未就绪时不执行。成功更新详情；失败保留旧值。 */
  setFavorite(enabled: boolean): void {
    const detail = this.detail;
    const movieId = this.movieId;
    const client = this.client();
    if (detail === null || movieId === null || client === null) {
      return;
    }
    if (this.status !== MovieDetailStatus.READY || this.favoriteInFlight || detail.isLimited()) {
      return;
    }
    const gen = this.generation;
    this.favoriteInFlight = true;
    this.favoriteError = null;
    client.setMovieFavorite(movieId, enabled).then(() => {
      if (gen !== this.generation) {
        return;
      }
      const current = this.detail;
      if (current !== null) {
        this.detail = current.withFavorite(enabled);
      }
      this.favoriteInFlight = false;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.favoriteInFlight = false;
      this.favoriteError = this.errorCodeOf(err);
      this.notifyChanged();
    });
  }

  /** 选择来源：仅 ready 且来源存在且非 rejected。 */
  selectSource(sourceId: string): void {
    const detail = this.detail;
    if (detail === null || this.status !== MovieDetailStatus.READY) {
      return;
    }
    if (this.sourceSelectable(detail, sourceId)) {
      this.selectedSourceId = sourceId;
    }
  }

  /** 来源重载/认证变化时由页面调用清空选择。 */
  clearSelection(): void {
    this.selectedSourceId = null;
    this.notifyChanged();
  }

  private sourceSelectable(detail: MovieDetail, sourceId: string): boolean {
    for (const source of detail.sources) {
      if (source.id === sourceId) {
        return source.isSelectable();
      }
    }
    return false;
  }

  private client(): ApiClient | null {
    return this.apiClient;
  }

  private errorCodeOf(err: Error): string {
    if (err instanceof ApiException) {
      return err.code;
    }
    if (err instanceof ProtocolException) {
      return 'client_protocol_error';
    }
    return 'client_transport_error';
  }
}
