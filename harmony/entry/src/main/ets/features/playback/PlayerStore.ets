/**
 * 播放器 Store（AC-099..106、AC-114）。
 *
 * - 初始 mode 固定 original；每次进入/显式重试/模式切换都 POST playback-sessions 新会话。
 * - manifest 必须匹配请求 mode/platform；stream_url 解析为同 origin 绝对 URL（capability URL）。
 * - 模式切换先创建新 session，成功原子替换并 reload surface，失败保留旧会话 + 错误动作。
 * - surface error：manifest 已过期时自动重签同 mode 一次（retriedOnce）；未过期或重签失败
 *   显示错误（重试 / original 下兼容播放），重复错误不循环。
 * - 起始位置：manifest.progress 非空 → surface.load 携带 startPositionMs（经 SeekCoordinator 执行）。
 * - generation 隔离：切换/销毁后旧异步响应丢弃。
 * - dispose：release surface + 清 session，不取消/清理 CacheJob。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, PlaybackManifest } from '../../core/api/ApiModels';

export enum PlaybackMode {
  ORIGINAL = 'original',
  COMPATIBILITY = 'compatibility',
}

export enum PlayerPhase {
  IDLE,
  CREATING_SESSION,
  PLAYING,
  PAUSED,
  COMPLETED,
  ERROR,
  RELEASED,
}

/** 播放 surface 端口（AVPlayerAdapter 实现；测试注入 Fake）。 */
export interface PlayerSurface {
  load(url: string, headers: Record<string, string>, startPositionMs: number): Promise<void>;
  play(): void;
  pause(): void;
  seek(timeMs: number): void;
  setSpeed(speed: number): void;
  release(): void;
}

@ObservedV2
export class PlayerStore {
  @Trace mode: PlaybackMode = PlaybackMode.ORIGINAL;
  @Trace phase: PlayerPhase = PlayerPhase.IDLE;
  @Trace session: PlaybackManifest | null = null;
  @Trace errorCode: string | null = null;
  @Trace positionMs: number = 0;
  @Trace durationMs: number = 0;
  @Trace speed: number = 1.0;
  @Trace fullscreen: boolean = false;

  private apiClient: ApiClient | null = null;
  private origin: string = '';
  private surface: PlayerSurface | null = null;
  private clientInstanceId: string = '';
  private cacheJobId: string | null = null;
  private mediaId: string | null = null;
  private retriedOnce: boolean = false;
  private generation: number = 0;
  private readonly changeListeners: (() => void)[] = [];

  attach(client: ApiClient | null, origin: string, surface: PlayerSurface | null,
    clientInstanceId: string): void {
    this.apiClient = client;
    this.origin = origin;
    this.surface = surface;
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

  /** 进入播放器：初始 original session（ready job 入口）。 */
  enter(cacheJobId: string, mediaId: string): void {
    this.cacheJobId = cacheJobId;
    this.mediaId = mediaId;
    this.mode = PlaybackMode.ORIGINAL;
    this.retriedOnce = false;
    this.createSession(PlaybackMode.ORIGINAL);
  }

  /** 用户显式重试：新建同 mode 会话。 */
  retry(): void {
    if (this.cacheJobId === null || this.mediaId === null) {
      return;
    }
    this.retriedOnce = false;
    this.createSession(this.mode);
  }

  /** 模式切换（原画/兼容播放）：先新 session，成功原子替换，失败保留旧会话；
   *  连续切换允许覆盖在途会话（generation 丢弃旧响应）。 */
  switchMode(mode: PlaybackMode): void {
    if (mode === this.mode || this.cacheJobId === null || this.mediaId === null) {
      return;
    }
    this.retriedOnce = false;
    this.createSession(mode);
  }

  /** surface stateChange：prepared → 开始播放。 */
  onSurfacePrepared(): void {
    if (this.phase === PlayerPhase.CREATING_SESSION) {
      this.phase = PlayerPhase.PLAYING;
      const surface = this.surface;
      if (surface !== null) {
        surface.play();
      }
      this.notifyChanged();
    }
  }

  /** surface timeUpdate（进度）。 */
  onSurfaceTimeUpdate(positionMs: number, durationMs: number): void {
    this.positionMs = positionMs;
    if (durationMs > 0) {
      this.durationMs = durationMs;
    }
    this.notifyChanged();
  }

  /** surface 完成。 */
  onSurfaceCompleted(): void {
    this.phase = PlayerPhase.COMPLETED;
    this.notifyChanged();
  }

  /** surface 错误：已过期自动重签同 mode 一次；否则进入 ERROR。 */
  onSurfaceError(err: Error): void {
    const session = this.session;
    if (session !== null && session.isExpired(Date.now()) && !this.retriedOnce) {
      // 过期重签一次（同 mode），不循环
      this.retriedOnce = true;
      this.createSession(this.mode);
      return;
    }
    this.phase = PlayerPhase.ERROR;
    this.errorCode = this.errorCodeOf(err);
    this.notifyChanged();
  }

  /** 播放/暂停（页面控制）。 */
  play(): void {
    if (this.phase === PlayerPhase.PAUSED || this.phase === PlayerPhase.COMPLETED) {
      this.phase = PlayerPhase.PLAYING;
      const surface = this.surface;
      if (surface !== null) {
        surface.play();
      }
      this.notifyChanged();
    }
  }

  pause(): void {
    if (this.phase === PlayerPhase.PLAYING) {
      this.phase = PlayerPhase.PAUSED;
      const surface = this.surface;
      if (surface !== null) {
        surface.pause();
      }
      this.notifyChanged();
    }
  }

  togglePlayPause(): void {
    if (this.phase === PlayerPhase.PLAYING) {
      this.pause();
    } else if (this.phase === PlayerPhase.PAUSED || this.phase === PlayerPhase.COMPLETED) {
      this.play();
    }
  }

  /** 进度 slider 拖拽结束/前进后退按钮：交给 surface（SeekCoordinator 串行合并）。 */
  seek(timeMs: number): void {
    const surface = this.surface;
    if (surface === null || this.phase === PlayerPhase.ERROR || this.phase === PlayerPhase.RELEASED) {
      return;
    }
    surface.seek(timeMs);
  }

  setSpeed(speed: number): void {
    this.speed = speed;
    const surface = this.surface;
    if (surface !== null) {
      surface.setSpeed(speed);
    }
    this.notifyChanged();
  }

  toggleFullscreen(): void {
    this.fullscreen = !this.fullscreen;
    this.notifyChanged();
  }

  /** 页面销毁：release surface + 清 session（不取消 CacheJob）。 */
  dispose(): void {
    this.generation++;
    const surface = this.surface;
    if (surface !== null) {
      surface.release();
    }
    this.surface = null;
    this.session = null;
    this.phase = PlayerPhase.RELEASED;
    this.errorCode = null;
    this.notifyChanged();
  }

  private createSession(mode: PlaybackMode): void {
    const client = this.apiClient;
    const jobId = this.cacheJobId;
    const mediaId = this.mediaId;
    if (client === null || jobId === null || mediaId === null) {
      this.phase = PlayerPhase.ERROR;
      this.errorCode = 'client_transport_error';
      this.notifyChanged();
      return;
    }
    const gen = ++this.generation;
    this.phase = PlayerPhase.CREATING_SESSION;
    this.errorCode = null;
    this.notifyChanged();
    client.createPlaybackSession(jobId, mediaId, mode, this.clientInstanceId).then((manifest: PlaybackManifest) => {
      if (gen !== this.generation) {
        return; // 已被切换/销毁覆盖
      }
      this.applyManifest(manifest, mode);
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.phase = PlayerPhase.ERROR;
      this.errorCode = this.errorCodeOf(err);
      this.notifyChanged();
    });
  }

  private applyManifest(manifest: PlaybackManifest, requestedMode: PlaybackMode): void {
    if (manifest.mode !== requestedMode) {
      // 契约：manifest 必须匹配请求 mode
      this.phase = PlayerPhase.ERROR;
      this.errorCode = 'client_protocol_error';
      this.notifyChanged();
      return;
    }
    this.session = manifest;
    this.mode = requestedMode;
    const surface = this.surface;
    if (surface === null) {
      return;
    }
    let url: string;
    try {
      url = PlayerStore.resolveStreamUrl(this.origin, manifest.streamUrl);
    } catch (err) {
      this.phase = PlayerPhase.ERROR;
      this.errorCode = 'client_protocol_error';
      this.notifyChanged();
      return;
    }
    const headers: Record<string, string> = { 'User-Agent': manifest.requiredUserAgent };
    // 起始 media 必须存在于 queue（契约 §3）
    let found = false;
    for (const item of manifest.mediaQueue) {
      if (item.mediaId === this.mediaId) {
        found = true;
        break;
      }
    }
    if (!found) {
      this.phase = PlayerPhase.ERROR;
      this.errorCode = 'client_protocol_error';
      this.notifyChanged();
      return;
    }
    const gen = this.generation;
    const startMs = manifest.progress !== null && !manifest.progress.completed ?
      manifest.progress.positionSeconds * 1000 : 0;
    surface.load(url, headers, startMs).then(() => {
      // load 完成：等待 surface onStateChange(prepared) → onSurfacePrepared → play
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return; // 旧 load 失败不落新会话
      }
      this.onSurfaceError(err);
    });
  }

  /** capability URL → 同 origin 绝对 URL（完整 URL 只存内存）。
   *  同源精确校验：origin 后必须紧跟 '/'（拒绝 test.evil/test@evil/test:8443 等前缀伪装）。 */
  static resolveStreamUrl(origin: string, url: string): string {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      if (!url.startsWith(origin)) {
        throw new Error('stream_url origin mismatch');
      }
      const rest = url.substring(origin.length);
      if (!rest.startsWith('/')) {
        throw new Error('stream_url origin mismatch');
      }
      return url;
    }
    if (url.startsWith('//')) {
      throw new Error('stream_url must not be protocol-relative');
    }
    if (url.startsWith('/')) {
      return origin + url;
    }
    throw new Error('stream_url must be absolute or root-relative');
  }

  private errorCodeOf(err: Error): string {
    if (err instanceof ApiException) {
      return err.code;
    }
    return 'client_transport_error';
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}
