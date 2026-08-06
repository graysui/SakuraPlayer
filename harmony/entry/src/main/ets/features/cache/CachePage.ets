/**
 * 缓存页（AC-118/122）。
 * - 固定容量三格（running 2 / queued 10 / ready 20）+ 服务端当前计数。
 * - 任务分页列表（每页 24）；取消/清理带二次确认，202 响应替换列表项；
 *   cancelling/cleaning 不提供重复操作；failed/cleaned/detached 只读。
 * - 事件快照变化触发当前列表刷新。
 */

import { CachePageStatus, CacheStore } from './CacheStore';
import { CacheJobDetail } from '../../core/api/ApiModels';
import { authStore } from '../../core/auth/AuthStore';

@Component
export struct CachePage {
  private store: CacheStore = new CacheStore();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  @State ready: boolean = false;
  @State failed: boolean = false;

  aboutToAppear(): void {
    this.store.attach(authStore.apiClientProvider, authStore.snapshotStore);
    this.store.addChangeListener(this.onStoreChanged);
    if (this.store.status === CachePageStatus.IDLE) {
      this.store.refresh();
    }
    this.syncFromStore();
  }

  aboutToDisappear(): void {
    this.store.removeChangeListener(this.onStoreChanged);
    this.store.detach();
  }

  private syncFromStore(): void {
    this.ready = this.store.status === CachePageStatus.READY;
    this.failed = this.store.status === CachePageStatus.FAILED;
  }

  private confirmCancel(job: CacheJobDetail): void {
    this.getUIContext().getPromptAction().showDialog({
      title: '取消缓存任务？',
      message: '任务将停止并进入安全清理。',
      buttons: [
        { text: '取消', color: $r('app.color.text_secondary') },
        { text: '确认取消', color: '#FF3B30' },
      ],
    }).then((result) => {
      if (result.index === 1) {
        this.store.cancelJob(job.id);
      }
    }).catch(() => {
      // 对话框关闭
    });
  }

  private confirmCleanup(job: CacheJobDetail): void {
    this.getUIContext().getPromptAction().showDialog({
      title: '清理缓存？',
      message: '仅删除应用管理目录中的已验证文件。',
      buttons: [
        { text: '取消', color: $r('app.color.text_secondary') },
        { text: '清理', color: '#FF3B30' },
      ],
    }).then((result) => {
      if (result.index === 1) {
        this.store.cleanupJob(job.id);
      }
    }).catch(() => {
      // 对话框关闭
    });
  }

  @Builder
  capacityBar() {
    Row({ space: 8 }) {
      Column({ space: 2 }) {
        Text(`${this.store.capacity !== null ? this.store.capacity.running : 0} / ${this.store.capacity !== null ? this.store.capacity.runningLimit : 2}`)
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor('#B4233A')
        Text('运行中')
          .fontSize(11)
          .fontColor($r('app.color.text_secondary'))
      }
      .layoutWeight(1)
      Column({ space: 2 }) {
        Text(`${this.store.capacity !== null ? this.store.capacity.queued : 0} / ${this.store.capacity !== null ? this.store.capacity.queuedLimit : 10}`)
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor('#667085')
        Text('排队中')
          .fontSize(11)
          .fontColor($r('app.color.text_secondary'))
      }
      .layoutWeight(1)
      Column({ space: 2 }) {
        Text(`${this.store.capacity !== null ? this.store.capacity.ready : 0} / ${this.store.capacity !== null ? this.store.capacity.readyLimit : 20}`)
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor('#12B76A')
        Text('可播放')
          .fontSize(11)
          .fontColor($r('app.color.text_secondary'))
      }
      .layoutWeight(1)
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12, bottom: 8 })
  }

  @Builder
  jobRow(job: CacheJobDetail) {
    Row({ space: 10 }) {
      Column({ space: 3 }) {
        Text(this.shortId(job.movieId))
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.text_primary'))
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
        Text(CacheStore.statusText(job.status))
          .fontSize(12)
          .fontColor(job.status === 'failed' || job.status === 'detached' ? '#FF3B30' : $r('app.color.text_secondary'))
        if (job.errorCode !== null) {
          Text(job.errorCode)
            .fontSize(11)
            .fontColor('#FF3B30')
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
        }
        if (job.remotePercent !== null) {
          Text(`${Math.round(job.remotePercent)}%`)
            .fontSize(11)
            .fontColor($r('app.color.text_secondary'))
        }
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
      if (CacheStore.canCancel(job) && !CacheStore.isBusy(job)) {
        Button('取消')
          .fontSize(12)
          .backgroundColor($r('app.color.surface_alt'))
          .fontColor($r('app.color.text_primary'))
          .enabled(this.store.actionJobId === null)
          .onClick(() => this.confirmCancel(job))
      }
      if (CacheStore.canCleanup(job) && !CacheStore.isBusy(job)) {
        Button('清理')
          .fontSize(12)
          .backgroundColor($r('app.color.surface_alt'))
          .fontColor($r('app.color.text_primary'))
          .enabled(this.store.actionJobId === null)
          .onClick(() => this.confirmCleanup(job))
      }
      if (CacheStore.isBusy(job)) {
        Text('处理中…')
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
      }
    }
    .width('100%')
    .height(96)
    .padding({ left: 16, right: 16, top: 12, bottom: 12 })
    .border({ width: { bottom: 0.5 }, color: $r('app.color.divider') })
  }

  private shortId(id: string): string {
    if (id.length <= 13) {
      return id;
    }
    return `${id.substring(0, 8)}…${id.substring(id.length - 4)}`;
  }

  build() {
    Column({ space: 0 }) {
      this.capacityBar()
      if (this.failed) {
        Column({ space: 10 }) {
          Text(this.store.errorMessage ?? '缓存任务加载失败')
            .fontSize(14)
            .fontColor($r('app.color.text_primary'))
          Button('重试')
            .fontSize(14)
            .onClick(() => this.store.refresh())
        }
        .justifyContent(FlexAlign.Center)
        .width('100%')
        .height('70%')
      } else if (this.store.items.length === 0 && this.store.status !== CachePageStatus.LOADING) {
        Column({ space: 8 }) {
          Text('暂无缓存任务')
            .fontSize(14)
            .fontColor($r('app.color.text_secondary'))
          Button('刷新')
            .fontSize(13)
            .onClick(() => this.store.refresh())
        }
        .justifyContent(FlexAlign.Center)
        .width('100%')
        .height('70%')
      } else {
        List({ space: 0 }) {
          ForEach(this.store.items, (job: CacheJobDetail) => {
            ListItem() {
              this.jobRow(job)
            }
          }, (job: CacheJobDetail) => job.id)
          if (this.store.nextCursor !== null) {
            ListItem() {
              Row() {
                Text(this.store.loadingMore ? '加载中…' : '加载更多')
                  .fontSize(13)
                  .fontColor($r('app.color.primary'))
                  .padding(12)
              }
              .justifyContent(FlexAlign.Center)
              .width('100%')
              .onClick(() => this.store.loadMore())
            }
          }
        }
        .width('100%')
        .layoutWeight(1)
        .scrollBar(BarState.Off)
      }
      if (this.store.errorMessage !== null) {
        Text(this.store.errorMessage)
          .fontSize(12)
          .fontColor('#FF3B30')
          .width('100%')
          .padding(8)
      }
    }
    .width('100%')
    .height('100%')
  }
}
