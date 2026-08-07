/**
 * Media Kit AVPlayer 适配器（AC-099/100/102/105）。
 *
 * - setUrlSource(url, {'User-Agent': required_user_agent})：固定 UA，302/Range/HLS 由
 *   AVPlayer 网络栈 + 后端流入口处理（客户端不解析 master/不选档位）。
 * - 生命周期：initialized → surfaceId → prepare → play；命名监听 release 前 off。
 * - seek 全部经 SeekCoordinator 串行合并；时间进度经 timeUpdate 上报。
 */

import { BusinessError } from '@kit.BasicServicesKit';
import { media } from '@kit.MediaKit';
import { PlayerSurface } from './PlayerStore';
import { TrackInfo, TrackSource } from './TrackStore';
import { SeekCallbacks, SeekCoordinator } from './SeekCoordinator';

/** 适配器事件回调（PlayerPage 注入，转发到 PlayerStore）。 */
export class AdapterCallbacks {
  readonly onPrepared: () => void;
  readonly onError: (err: Error) => void;
  readonly onTimeUpdate: (positionMs: number, durationMs: number) => void;
  readonly onCompleted: () => void;

  constructor(onPrepared: () => void, onError: (err: Error) => void,
    onTimeUpdate: (positionMs: number, durationMs: number) => void,
    onCompleted: () => void) {
    this.onPrepared = onPrepared;
    this.onError = onError;
    this.onTimeUpdate = onTimeUpdate;
    this.onCompleted = onCompleted;
  }
}

export class AVPlayerAdapter implements PlayerSurface, TrackSource {
  private player: media.AVPlayer | null = null;
  private readonly surfaceId: string;
  private readonly callbacks: AdapterCallbacks;
  private readonly seekCoordinator: SeekCoordinator;
  private loaded: boolean = false;
  private released: boolean = false;
  private prepared: boolean = false;

  constructor(surfaceId: string, callbacks: AdapterCallbacks) {
    this.surfaceId = surfaceId;
    this.callbacks = callbacks;
    this.seekCoordinator = new SeekCoordinator((timeMs: number): void => {
      const player = this.player;
      if (player !== null && this.loaded) {
        // prepare resolve 后真实状态已 prepared（loaded 标志比事件可靠）
        player.seek(timeMs);
      }
    }, new SeekCallbacks(
      (): void => {
        this.seekCoordinator.onSeekDone();
      },
      (err: Error): void => {
        this.callbacks.onError(err);
      }));
  }

  /** 创建 AVPlayer + 命名监听（prepare 前调用一次）。 */
  private async ensurePlayer(): Promise<media.AVPlayer> {
    if (this.player !== null) {
      return this.player;
    }
    const player = await media.createAVPlayer();
    this.player = player;
    player.on('stateChange', (state: media.AVPlayerState, reason: media.StateChangeReason): void => {
      if (state === 'prepared') {
        this.prepared = true;
        this.callbacks.onPrepared();
      } else if (state === 'completed') {
        this.callbacks.onCompleted();
      } else if (state === 'error') {
        this.callbacks.onError(new Error(`avplayer state error: ${reason}`));
      }
    });
    player.on('error', (err: BusinessError): void => {
      this.callbacks.onError(new Error(err.message));
    });
    player.on('timeUpdate', (timeMs: number): void => {
      const duration = this.player === null ? 0 : this.player.duration;
      this.callbacks.onTimeUpdate(timeMs, duration);
    });
    player.on('seekDone', (): void => {
      // seek 完成：推进串行协调器（AC-105）
      this.seekCoordinator.onSeekDone();
    });
    return player;
  }

  async load(url: string, headers: Record<string, string>, startPositionMs: number): Promise<void> {
    if (this.released) {
      throw new Error('player released');
    }
    const player = await this.ensurePlayer();
    if (this.loaded) {
      // 模式切换/重试：AVPlayer 状态机只允许 initialized/stopped 重新 setMediaSource
      player.stop();
      this.prepared = false;
    }
    player.surfaceId = this.surfaceId;
    // 固定 UA：createMediaSourceWithUrl 注入 header，后端 capability 校验同一 UA（AC-100/102）
    const source = media.createMediaSourceWithUrl(url, headers);
    await player.setMediaSource(source);
    await player.prepare();
    this.loaded = true;
    if (startPositionMs > 0) {
      // prepare resolve 后真实状态已 prepared（事件可能未派发）；续播 seek 经协调器
      this.seekCoordinator.request(startPositionMs);
    }
  }

  /** 枚举音视频/字幕轨道（prepared/playing/paused 后）。 */
  async getTracks(): Promise<TrackInfo[]> {
    const player = this.player;
    if (player === null) {
      return new Array<TrackInfo>();
    }
    const descs = await player.getTrackDescription();
    const result: TrackInfo[] = [];
    for (let i = 0; i < descs.length; i++) {
      const rawType = descs[i][media.MediaDescriptionKey.MD_KEY_TRACK_TYPE];
      const type = typeof rawType === 'number' ? rawType as number : -1;
      if (type === media.MediaType.MEDIA_TYPE_AUD) {
        result.push(new TrackInfo(i, 'audio', `音轨 ${result.length + 1}`));
      } else if (type === media.MediaType.MEDIA_TYPE_SUBTITLE) {
        result.push(new TrackInfo(i, 'subtitle', `字幕 ${result.length + 1}`));
      } else if (type === media.MediaType.MEDIA_TYPE_VID) {
        result.push(new TrackInfo(i, 'video', '视频'));
      }
    }
    return result;
  }

  async selectTrack(index: number): Promise<void> {
    const player = this.player;
    if (player === null) {
      return;
    }
    await player.selectTrack(index);
  }

  async deselectTrack(index: number): Promise<void> {
    const player = this.player;
    if (player === null) {
      return;
    }
    await player.deselectTrack(index);
  }

  /** 外置字幕（本地缓存文件 URL；API 24 签名已核验）。 */
  async addSubtitle(url: string): Promise<void> {
    const player = this.player;
    if (player === null) {
      return;
    }
    await player.addSubtitleFromUrl(url);
  }

  play(): void {
    const player = this.player;
    if (player !== null && (this.prepared || this.loaded)) {
      player.play();
    }
  }

  pause(): void {
    const player = this.player;
    if (player !== null && this.loaded) {
      player.pause();
    }
  }

  /** 唯一 seek 入口：串行合并（AC-105）。 */
  seek(timeMs: number): void {
    this.seekCoordinator.request(timeMs);
  }

  setSpeed(speed: number): void {
    const player = this.player;
    if (player === null || !this.prepared) {
      return;
    }
    const speeds: media.PlaybackSpeed[] = [
      media.PlaybackSpeed.SPEED_FORWARD_0_50_X,
      media.PlaybackSpeed.SPEED_FORWARD_0_75_X,
      media.PlaybackSpeed.SPEED_FORWARD_1_00_X,
      media.PlaybackSpeed.SPEED_FORWARD_1_25_X,
      media.PlaybackSpeed.SPEED_FORWARD_1_50_X,
      media.PlaybackSpeed.SPEED_FORWARD_2_00_X,
    ];
    let index = 2; // 1.0x
    if (speed <= 0.5) {
      index = 0;
    } else if (speed <= 0.75) {
      index = 1;
    } else if (speed <= 1.0) {
      index = 2;
    } else if (speed <= 1.25) {
      index = 3;
    } else if (speed <= 1.5) {
      index = 4;
    } else {
      index = 5;
    }
    player.setSpeed(speeds[index]);
  }

  release(): void {
    this.released = true;
    this.seekCoordinator.reset();
    const player = this.player;
    if (player === null) {
      return;
    }
    player.off('stateChange');
    player.off('error');
    player.off('timeUpdate');
    player.off('seekDone');
    player.release();
    this.player = null;
    this.loaded = false;
    this.prepared = false;
  }
}
