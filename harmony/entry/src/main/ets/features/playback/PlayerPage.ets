/**
 * 应用内播放器页（AC-099..106、AC-114）。
 *
 * - XComponent surface → AVPlayerAdapter（固定 UA/原画或 HLS/302 跟随由后端流入口 + AVPlayer 网络栈）。
 * - 深色控制层：播放/暂停、进度 slider（onChangeEnd 才 seek）、当前位置/总时长、倍速菜单、
 *   全屏（window 全屏 + 横屏 + keepScreenOn）、模式菜单（原画/兼容播放）、错误重试。
 * - 无缩略图、无外部播放器；控制区固定高度不重叠；横竖屏/全屏适配。
 * - 页面销毁：store.dispose() 释放 surface 与 session（不取消 CacheJob）。
 */

import { window } from '@kit.ArkUI';
import { authStore } from '../../core/auth/AuthStore';
import { PlaybackMode, PlayerPhase, PlayerStore } from './PlayerStore';
import { AVPlayerAdapter, AdapterCallbacks } from './AVPlayerAdapter';
import { PlaybackParam } from '../cache/playRequestCoordinator';

@Component
export struct PlayerPage {
  @Require pathStack: NavPathStack;
  @Prop cacheJobId: string = '';
  @Prop mediaId: string = '';

  private xcompController: XComponentController = new XComponentController();
  private store: PlayerStore = new PlayerStore();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  private screenOn: boolean = false;
  private orientationLandscape: boolean = false;
  private surfaceLoaded: boolean = false;
  private pageVisible: boolean = true;

  @State phase: PlayerPhase = PlayerPhase.IDLE;
  @State mode: PlaybackMode = PlaybackMode.ORIGINAL;
  @State errorCode: string | null = null;
  @State positionMs: number = 0;
  @State durationMs: number = 0;
  @State speed: number = 1.0;
  @State fullscreen: boolean = false;
  @State surfaceReady: boolean = false;
  @State speedMenuOpen: boolean = false;
  @State modeMenuOpen: boolean = false;

  aboutToAppear(): void {
    this.store.addChangeListener(this.onStoreChanged);
    this.syncFromStore();
  }

  aboutToDisappear(): void {
    this.store.removeChangeListener(this.onStoreChanged);
    this.store.dispose();
    this.restoreWindow();
  }

  /** 页面隐藏：暂停播放并恢复 keepScreenOn（不申请后台长时播放能力）。 */
  onPageHide(): void {
    this.pageVisible = false;
    this.store.pause();
    this.restoreWindow();
  }

  onPageShow(): void {
    this.pageVisible = true;
    // 回前台不自动恢复播放（用户显式操作）；fullscreen 状态由 store 保留
  }

  private syncFromStore(): void {
    this.phase = this.store.phase;
    this.mode = this.store.mode;
    this.errorCode = this.store.errorCode;
    this.positionMs = this.store.positionMs;
    this.durationMs = this.store.durationMs;
    this.speed = this.store.speed;
    this.fullscreen = this.store.fullscreen;
    this.surfaceReady = this.store.session !== null;
  }

  /** XComponent surface 就绪：创建 adapter + store 接线 + 进入播放（防重入）。 */
  private onSurfaceLoad(): void {
    if (this.surfaceLoaded) {
      return;
    }
    this.surfaceLoaded = true;
    const surfaceId = this.xcompController.getXComponentSurfaceId();
    const adapter = new AVPlayerAdapter(surfaceId, new AdapterCallbacks(
      (): void => {
        // 页面隐藏时不得自动开始播放（无后台长时播放能力）
        if (this.pageVisible) {
          this.store.onSurfacePrepared();
        }
      },
      (err: Error): void => {
        this.store.onSurfaceError(err);
      },
      (positionMs: number, durationMs: number): void => {
        this.store.onSurfaceTimeUpdate(positionMs, durationMs);
      },
      (): void => {
        this.store.onSurfaceCompleted();
      }));
    this.store.attach(authStore.apiClientProvider, authStore.serverBaseUrl, adapter,
      authStore.clientInstanceId);
    this.store.enter(this.cacheJobId, this.mediaId);
  }

  private formatTime(ms: number): string {
    const totalSeconds = Math.floor(ms / 1000);
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    const mm = m < 10 ? `0${m}` : `${m}`;
    const ss = s < 10 ? `0${s}` : `${s}`;
    if (h > 0) {
      return `${h}:${mm}:${ss}`;
    }
    return `${mm}:${ss}`;
  }

  private toggleFullscreen(): void {
    this.store.toggleFullscreen();
    const appContext = getContext(this);
    window.getLastWindow(appContext).then((win: window.Window) => {
      if (this.store.fullscreen) {
        win.setWindowLayoutFullScreen(true);
        win.setPreferredOrientation(window.Orientation.LANDSCAPE);
        win.setWindowKeepScreenOn(true);
        this.screenOn = true;
        this.orientationLandscape = true;
      } else {
        win.setWindowLayoutFullScreen(false);
        win.setPreferredOrientation(window.Orientation.PORTRAIT);
        win.setWindowKeepScreenOn(false);
        this.screenOn = false;
        this.orientationLandscape = false;
      }
    }).catch(() => {
      // 全屏切换失败：保持应用内播放可用
    });
  }

  private restoreWindow(): void {
    if (!this.screenOn && !this.orientationLandscape) {
      return;
    }
    const appContext = getContext(this);
    window.getLastWindow(appContext).then((win: window.Window) => {
      win.setWindowLayoutFullScreen(false);
      win.setPreferredOrientation(window.Orientation.PORTRAIT);
      win.setWindowKeepScreenOn(false);
      this.screenOn = false;
      this.orientationLandscape = false;
    }).catch(() => {
      // 恢复失败忽略
    });
  }

  @Builder
  videoSurface() {
    XComponent({ id: 'player-surface', type: 'surface', controller: this.xcompController })
      .width('100%')
      .height('100%')
      .backgroundColor('#000000')
      .onLoad(() => {
        this.onSurfaceLoad();
      })
  }

  @Builder
  controlBar() {
    Row({ space: 10 }) {
      Button(this.phase === PlayerPhase.PLAYING ? '暂停' : '播放')
        .fontSize(14)
        .fontColor('#FFFFFF')
        .backgroundColor('#33FFFFFF')
        .width(64)
        .height(36)
        .enabled(this.phase === PlayerPhase.PLAYING || this.phase === PlayerPhase.PAUSED ||
          this.phase === PlayerPhase.COMPLETED)
        .onClick(() => {
          this.store.togglePlayPause();
        })
      Text(this.formatTime(this.positionMs))
        .fontSize(12)
        .fontColor('#CCFFFFFF')
      Slider({
        value: this.positionMs,
        min: 0,
        max: this.durationMs > 0 ? this.durationMs : 1,
        step: 1,
      })
        .layoutWeight(1)
        .selectedColor('#FF9F43')
        .onChange((value: number, mode: SliderChangeMode) => {
          if (mode === SliderChangeMode.End) {
            this.store.seek(value);
          }
        })
      Text(this.formatTime(this.durationMs))
        .fontSize(12)
        .fontColor('#CCFFFFFF')
      Button(`${this.speed}x`)
        .fontSize(13)
        .fontColor('#FFFFFF')
        .backgroundColor('#33FFFFFF')
        .height(36)
        .onClick(() => {
          this.speedMenuOpen = !this.speedMenuOpen;
          this.modeMenuOpen = false;
        })
      Button('全屏')
        .fontSize(13)
        .fontColor('#FFFFFF')
        .backgroundColor('#33FFFFFF')
        .height(36)
        .onClick(() => {
          this.toggleFullscreen();
        })
    }
    .width('100%')
    .height(44)
    .padding({ left: 8, right: 8 })
  }

  @Builder
  speedMenu() {
    if (this.speedMenuOpen) {
      Column({ space: 2 }) {
        ForEach([0.75, 1.0, 1.25, 1.5, 2.0], (value: number) => {
          Button(`${value}x`)
            .fontSize(13)
            .fontColor(value === this.speed ? '#FF9F43' : '#FFFFFF')
            .backgroundColor('#33000000')
            .width(96)
            .height(34)
            .onClick(() => {
              this.store.setSpeed(value);
              this.speedMenuOpen = false;
            })
        }, (value: number) => `${value}`)
      }
      .padding(4)
      .backgroundColor('#66000000')
      .borderRadius(8)
      .position({ x: 40, y: 10 })
    }
  }

  @Builder
  modeMenu() {
    if (this.modeMenuOpen) {
      Column({ space: 2 }) {
        Button(this.mode === PlaybackMode.ORIGINAL ? '原画 ✓' : '原画')
          .fontSize(13)
          .fontColor('#FFFFFF')
          .backgroundColor('#33000000')
          .width(120)
          .height(34)
          .onClick(() => {
            this.store.switchMode(PlaybackMode.ORIGINAL);
            this.modeMenuOpen = false;
          })
        Button(this.mode === PlaybackMode.COMPATIBILITY ? '兼容播放 ✓' : '兼容播放')
          .fontSize(13)
          .fontColor('#FFFFFF')
          .backgroundColor('#33000000')
          .width(120)
          .height(34)
          .onClick(() => {
            this.store.switchMode(PlaybackMode.COMPATIBILITY);
            this.modeMenuOpen = false;
          })
      }
      .padding(4)
      .backgroundColor('#66000000')
      .borderRadius(8)
      .position({ x: 40, y: 10 })
    }
  }

  @Builder
  errorView() {
    Column({ space: 12 }) {
      Text('播放失败')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor('#FFFFFF')
      Text(this.errorCode ?? '未知错误')
        .fontSize(12)
        .fontColor('#CCFFFFFF')
      Row({ space: 10 }) {
        Button('重试')
          .fontSize(14)
          .fontColor('#FFFFFF')
          .backgroundColor('#FF9F43')
          .height(40)
          .onClick(() => {
            this.store.retry();
          })
        if (this.mode === PlaybackMode.ORIGINAL) {
          Button('兼容播放')
            .fontSize(14)
            .fontColor('#FFFFFF')
            .backgroundColor('#33FFFFFF')
            .height(40)
            .onClick(() => {
              this.store.switchMode(PlaybackMode.COMPATIBILITY);
            })
        }
      }
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  @Builder
  topBar() {
    Row() {
      Button('返回')
        .fontSize(14)
        .fontColor('#FFFFFF')
        .backgroundColor('#33FFFFFF')
        .height(36)
        .onClick(() => {
          this.pathStack.pop();
        })
      Blank()
      Button(this.mode === PlaybackMode.ORIGINAL ? '原画' : '兼容播放')
        .fontSize(13)
        .fontColor('#FFFFFF')
        .backgroundColor('#33FFFFFF')
        .height(36)
        .onClick(() => {
          this.modeMenuOpen = !this.modeMenuOpen;
          this.speedMenuOpen = false;
        })
    }
    .width('100%')
    .height(44)
    .padding({ left: 8, right: 8 })
  }

  build() {
    Stack({ alignContent: Alignment.Bottom }) {
      this.videoSurface()
      if (this.phase === PlayerPhase.ERROR) {
        this.errorView()
      } else if (this.phase === PlayerPhase.IDLE || this.phase === PlayerPhase.CREATING_SESSION) {
        Text('正在准备播放…')
          .fontSize(15)
          .fontColor('#CCFFFFFF')
      }
      Column({ space: 4 }) {
        this.topBar()
        Blank()
        if (this.phase === PlayerPhase.PLAYING || this.phase === PlayerPhase.PAUSED ||
          this.phase === PlayerPhase.COMPLETED) {
          this.controlBar()
        }
      }
      .width('100%')
      .height('100%')
      .onClick(() => {
        // 点击视频区无操作；控制栏常显
      })
      this.speedMenu()
      this.modeMenu()
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
  }
}
