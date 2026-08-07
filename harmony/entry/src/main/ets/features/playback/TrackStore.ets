/**
 * 轨道 Store（AC-107/109）：内嵌字幕/音轨枚举 + 外置字幕选择，字幕失败隔离。
 *
 * - TrackSource 端口（AVPlayerAdapter 实现；测试注入 Fake）。
 * - refreshTracks：prepared 后枚举内嵌轨道 + 下载并加载 manifest 外置字幕。
 * - 外置字幕：SubtitleCache 下载到私有缓存 → addSubtitle；下载/加载失败只记 error，
 *   不阻止视频（AC-109）。
 * - 倍速由 TASK-310 PlayerStore 提供（本 Store 专注轨道）。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { PlaybackManifest, SubtitleOption } from '../../core/api/ApiModels';
import { SubtitleCache } from '../../core/storage/SubtitleCache';
import { common } from '@kit.AbilityKit';

/** 轨道信息（selectTrack 的 index + 展示标签）。 */
export class TrackInfo {
  readonly index: number;
  readonly kind: string; // 'audio' | 'video' | 'subtitle'
  readonly label: string;

  constructor(index: number, kind: string, label: string) {
    this.index = index;
    this.kind = kind;
    this.label = label;
  }
}

/** 播放器轨道端口（AVPlayerAdapter 实现；测试注入 Fake）。 */
export interface TrackSource {
  getTracks(): Promise<TrackInfo[]>;
  selectTrack(index: number): Promise<void>;
  deselectTrack(index: number): Promise<void>;
  addSubtitle(url: string): Promise<void>;
}

@ObservedV2
export class TrackStore {
  @Trace embeddedSubtitles: TrackInfo[] = [];
  @Trace audioTracks: TrackInfo[] = [];
  @Trace externalSubtitles: SubtitleOption[] = [];
  @Trace selectedEmbeddedIndex: number | null = null;
  @Trace selectedAudioIndex: number | null = null;
  @Trace selectedExternalId: string | null = null;
  @Trace subtitleError: string | null = null;
  @Trace tracksReady: boolean = false;

  private source: TrackSource | null = null;
  private manifest: PlaybackManifest | null = null;
  private readonly changeListeners: (() => void)[] = [];

  attach(source: TrackSource | null, manifest: PlaybackManifest | null): void {
    this.source = source;
    this.manifest = manifest;
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

  /** prepared 后：枚举内嵌轨道 + 加载外置字幕（失败隔离）。 */
  async refreshTracks(context: common.Context, client: ApiClient | null): Promise<void> {
    const source = this.source;
    const manifest = this.manifest;
    this.subtitleError = null;
    if (source === null) {
      this.tracksReady = false;
      this.notifyChanged();
      return;
    }
    try {
      const tracks = await source.getTracks();
      this.embeddedSubtitles = new Array<TrackInfo>();
      this.audioTracks = new Array<TrackInfo>();
      for (const track of tracks) {
        if (track.kind === 'subtitle') {
          this.embeddedSubtitles.push(track);
        } else if (track.kind === 'audio') {
          this.audioTracks.push(track);
        }
      }
    } catch (err) {
      // 轨道枚举失败：不阻止播放
      this.embeddedSubtitles = new Array<TrackInfo>();
      this.audioTracks = new Array<TrackInfo>();
    }
    // 外置字幕：manifest 授权集合（AC-109）
    this.externalSubtitles = manifest === null ? new Array<SubtitleOption>() : manifest.subtitles;
    for (const sub of this.externalSubtitles) {
      if (sub.selectedByDefault && this.selectedExternalId === null) {
        this.selectedExternalId = sub.id;
        const ok = await this.loadExternal(context, client, sub);
        if (!ok) {
          this.subtitleError = 'subtitle_load_failed';
        }
      }
    }
    this.tracksReady = true;
    this.notifyChanged();
  }

  /** 选择外置字幕（切换）：下载 + 加载；失败回滚选中并记 error（不阻止视频）。 */
  async selectExternal(context: common.Context, client: ApiClient | null,
    sub: SubtitleOption): Promise<void> {
    const previous = this.selectedExternalId;
    this.selectedExternalId = sub.id;
    this.selectedEmbeddedIndex = null;
    const ok = await this.loadExternal(context, client, sub);
    if (!ok) {
      this.subtitleError = 'subtitle_load_failed';
      this.selectedExternalId = previous; // 回滚：菜单不显示已加载的字幕
    }
    this.notifyChanged();
  }

  /** 选择内嵌字幕轨。 */
  selectEmbedded(track: TrackInfo): void {
    const source = this.source;
    if (source === null) {
      return;
    }
    this.selectedEmbeddedIndex = track.index;
    this.selectedExternalId = null;
    source.selectTrack(track.index).catch(() => {
      this.subtitleError = 'embedded_select_failed';
      this.notifyChanged();
    });
    this.notifyChanged();
  }

  /** 取消字幕选择（deselect 当前内嵌轨；外置无 deselect 语义）。 */
  deselectSubtitle(): void {
    const source = this.source;
    if (source === null) {
      return;
    }
    if (this.selectedEmbeddedIndex !== null) {
      const index = this.selectedEmbeddedIndex;
      source.deselectTrack(index).catch(() => {
        // deselect 失败忽略
      });
      this.selectedEmbeddedIndex = null;
    }
    this.selectedExternalId = null;
    this.notifyChanged();
  }

  /** 选择音轨。 */
  selectAudio(track: TrackInfo): void {
    const source = this.source;
    if (source === null) {
      return;
    }
    this.selectedAudioIndex = track.index;
    source.selectTrack(track.index).catch(() => {
      // 音轨切换失败忽略（保持当前）
    });
    this.notifyChanged();
  }

  private async loadExternal(context: common.Context, client: ApiClient | null,
    sub: SubtitleOption): Promise<boolean> {
    const source = this.source;
    const manifest = this.manifest;
    if (source === null || manifest === null) {
      return false;
    }
    // 私有缓存下载（同名优先）；失败返回 null
    const path = await SubtitleCache.download(context, client, sub, manifest.cacheJobId);
    if (path === null) {
      return false;
    }
    try {
      // 外置字幕经 file:// URL 加载（API 24 签名已核验；真实行为留设备验证）
      await source.addSubtitle(`file://${path}`);
      return true;
    } catch (err) {
      return false;
    }
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}
