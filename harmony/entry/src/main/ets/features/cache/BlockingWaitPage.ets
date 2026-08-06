/**
 * 60 秒全屏阻断等待页（AC-086/087/088）。
 *
 * - 只由 PlayRequestStore 的 started 状态进入；全屏 NavDestination 覆盖 tab/搜索。
 * - NavDestination.onBackPressed 拦系统返回：唯一取消出口是按钮 + 二次确认。
 * - 剩余秒数 1s 递减（ceil 显示）；固定容量 2/10 只读展示。
 * - 60 秒内 snapshot 同 job ready → 自动导航播放器（一次）；超时 → 显示切换来源提示
 *   （不取消任务，任务继续后台）；取消成功 → 返回；失败 → 保留等待页 + 错误文案。
 * - 页面销毁：detach 清 timer/listener；后台 ready 不自动导航。
 */

import { PlayRequestPhase, PlayRequestStore } from './PlayRequestStore';
import { PlaybackParam } from './playRequestCoordinator';
import { CancelDialogParams, closeCancelDialog, openCancelDialog } from './CancelDialog';
import { ComponentContent } from '@kit.ArkUI';
import { authStore } from '../../core/auth/AuthStore';
import { playRequestStore } from './playRequestCoordinator';

@Component
export struct BlockingWaitPage {
  @Require pathStack: NavPathStack;
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  private dialogContent: ComponentContent<CancelDialogParams> | null = null;
  private navigated: boolean = false;

  @State phase: PlayRequestPhase = PlayRequestPhase.IDLE;
  @State remainingSeconds: number = 0;
  @State cancelError: string | null = null;
  @State cancelling: boolean = false;

  aboutToAppear(): void {
    playRequestStore.addChangeListener(this.onStoreChanged);
    this.syncFromStore();
  }

  aboutToDisappear(): void {
    playRequestStore.removeChangeListener(this.onStoreChanged);
    this.closeDialog();
    // 页面退出统一清理（系统返回/CANCELLED/READY 导航等路径；重复 reset 无害）
    if (playRequestStore.phase === PlayRequestPhase.WAITING ||
      playRequestStore.phase === PlayRequestPhase.TIMED_OUT ||
      playRequestStore.phase === PlayRequestPhase.FAILED ||
      playRequestStore.phase === PlayRequestPhase.QUEUED ||
      playRequestStore.phase === PlayRequestPhase.EXISTING ||
      playRequestStore.phase === PlayRequestPhase.READY) {
      playRequestStore.reset();
    }
  }

  private syncFromStore(): void {
    this.phase = playRequestStore.phase;
    this.remainingSeconds = playRequestStore.remainingSeconds;
    this.cancelError = playRequestStore.cancelError;
    this.cancelling = playRequestStore.cancelling;
    if (playRequestStore.phase === PlayRequestPhase.CANCELLED && !this.navigated) {
      // 取消成功：自动退出等待页回详情（契约 §4）
      this.navigated = true;
      playRequestStore.reset();
      this.pathStack.pop();
      return;
    }
    if (playRequestStore.phase === PlayRequestPhase.READY && !this.navigated) {
      // 60 秒内完成：自动导航播放器（navigated 去重，进入即 READY 也触发）
      this.navigated = true;
      const job = playRequestStore.job;
      if (job !== null) {
        // 替换等待页为播放器（一次）
        const playback: PlaybackParam = {
          cacheJobId: job.id,
          mediaId: job.selectedMediaIds.length > 0 ? job.selectedMediaIds[0] : null,
        };
        this.pathStack.replacePathByName('Player', playback);
      }
    }
  }

  private confirmCancel(): void {
    if (this.cancelling) {
      return;
    }
    this.dialogContent = openCancelDialog(this.getUIContext(), (confirmed: boolean): void => {
      // 对话框已自关闭：释放引用（下一次打开复用新 content）
      this.dialogContent = null;
      if (confirmed) {
        playRequestStore.cancel(true);
      }
    });
  }

  private closeDialog(): void {
    if (this.dialogContent !== null) {
      closeCancelDialog(this.getUIContext(), this.dialogContent);
      this.dialogContent = null;
    }
  }

  private statusText(): string {
    const job = playRequestStore.job;
    const status = job === null ? '' : job.status;
    if (status === 'submitting') {
      return '正在提交离线任务';
    }
    if (status === 'offlining') {
      return '115 正在离线下载';
    }
    if (status === 'submit_uncertain') {
      return '正在确认任务状态';
    }
    if (status === 'resolving') {
      return '正在解析媒体文件';
    }
    if (status === 'awaiting_selection') {
      return '需要在缓存页选择媒体文件';
    }
    return '等待状态更新';
  }

  @Builder
  waitView() {
    Column({ space: 16 }) {
      Column({ space: 8 }) {
        SymbolGlyph($r('sys.symbol.clock'))
          .fontSize(44)
          .fontColor([$r('app.color.primary')])
        Text('正在准备播放')
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor($r('app.color.text_primary'))
        Text(this.statusText())
          .fontSize(14)
          .fontColor($r('app.color.text_secondary'))
        Text(`剩余 ${this.remainingSeconds} 秒`)
          .fontSize(24)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.primary'))
        Progress({ value: this.remainingSeconds, total: 60 })
          .width(220)
          .color($r('app.color.primary'))
      }
      .width('100%')
      .margin({ top: 80 })

      Text('最多 2 个任务同时运行、10 个排队等待')
        .fontSize(12)
        .fontColor($r('app.color.text_secondary'))
      Text('关闭页面不会取消缓存任务')
        .fontSize(12)
        .fontColor($r('app.color.text_secondary'))
      if (this.cancelError !== null) {
        Text(`取消失败，请重试（${this.cancelError}）`)
          .fontSize(12)
          .fontColor('#FF3B30')
      }
      Button('取消等待')
        .fontSize(14)
        .backgroundColor($r('app.color.surface_alt'))
        .fontColor('#FF3B30')
        .width(200)
        .height(44)
        .enabled(!this.cancelling)
        .onClick(() => this.confirmCancel())
    }
    .justifyContent(FlexAlign.Start)
    .width('100%')
    .height('100%')
  }

  @Builder
  timedOutView() {
    Column({ space: 12 }) {
      SymbolGlyph($r('sys.symbol.exclamationmark'))
        .fontSize(40)
        .fontColor([$r('app.color.text_secondary')])
      Text('等待已结束，请切换来源')
        .fontSize(17)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
      Text('缓存任务会继续运行，完成后将收到通知')
        .fontSize(13)
        .fontColor($r('app.color.text_secondary'))
        .textAlign(TextAlign.Center)
        .width('80%')
      Button('返回')
        .fontSize(14)
        .width(200)
        .height(44)
        .margin({ top: 12 })
        .onClick(() => {
          playRequestStore.reset();
          this.pathStack.pop();
        })
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  @Builder
  failedView() {
    Column({ space: 12 }) {
      Text('播放请求失败')
        .fontSize(17)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
      Text(playRequestStore.errorCode ?? '未知错误')
        .fontSize(13)
        .fontColor($r('app.color.text_secondary'))
      Button('返回')
        .fontSize(14)
        .width(200)
        .height(44)
        .onClick(() => {
          playRequestStore.reset();
          this.pathStack.pop();
        })
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  @Builder
  queuedView() {
    Column({ space: 12 }) {
      SymbolGlyph($r('sys.symbol.clock'))
        .fontSize(40)
        .fontColor([$r('app.color.text_secondary')])
      Text('任务已加入排队，不会自动播放')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
      Text('开始执行或完成时会收到通知')
        .fontSize(13)
        .fontColor($r('app.color.text_secondary'))
      Button('返回')
        .fontSize(14)
        .width(200)
        .height(44)
        .margin({ top: 12 })
        .onClick(() => {
          playRequestStore.reset();
          this.pathStack.pop();
        })
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  build() {
    NavDestination() {
      if (this.phase === PlayRequestPhase.WAITING) {
        this.waitView()
      } else if (this.phase === PlayRequestPhase.READY) {
        Column({ space: 12 }) {
          Text('任务已就绪，正在进入播放…')
            .fontSize(16)
            .fontColor($r('app.color.text_primary'))
          Button('返回')
            .fontSize(14)
            .width(200)
            .height(44)
            .onClick(() => {
              playRequestStore.reset();
              this.pathStack.pop();
            })
        }
        .justifyContent(FlexAlign.Center)
        .width('100%')
        .height('100%')
      } else if (this.phase === PlayRequestPhase.TIMED_OUT) {
        this.timedOutView()
      } else if (this.phase === PlayRequestPhase.FAILED) {
        this.failedView()
      } else if (this.phase === PlayRequestPhase.QUEUED) {
        this.queuedView()
      } else if (this.phase === PlayRequestPhase.CANCELLED || this.phase === PlayRequestPhase.EXISTING) {
        Column({ space: 12 }) {
          Text(this.phase === PlayRequestPhase.CANCELLED ? '任务已取消' : '任务已存在，等待后台事件')
            .fontSize(16)
            .fontColor($r('app.color.text_primary'))
          Button('返回')
            .fontSize(14)
            .width(200)
            .height(44)
            .onClick(() => {
              playRequestStore.reset();
              this.pathStack.pop();
            })
        }
        .justifyContent(FlexAlign.Center)
        .width('100%')
        .height('100%')
      }
    }
    .title('正在准备播放')
    .backgroundColor($r('app.color.background'))
    .onBackPressed(() => {
      // 全屏锁：WAITING 时系统返回只拦截（契约：取消唯一出口是按钮二次确认）
      return this.phase === PlayRequestPhase.WAITING;
    })
    .hideTitleBar(true)
  }
}
