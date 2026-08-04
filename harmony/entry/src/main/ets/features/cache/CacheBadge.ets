/**
 * 顶部缓存入口角标（AC-118）：显示 queued/running/ready 计数。
 * 数据源：事件快照的 QueueDiagnostic（SnapshotStore.queues），
 * 快照恢复/变化时自动刷新；计数 >99 显示 99+。
 */

import { SnapshotListener, SnapshotStore } from '../../core/events/SnapshotStore';

@Component
export struct CacheBadge {
  @State queued: number = 0;
  @State running: number = 0;
  @State ready: number = 0;
  private snapshot: SnapshotStore | null = null;
  private listener: SnapshotListener = (): void => {
    this.refresh();
  };

  aboutToAppear(): void {
    if (this.snapshot !== null) {
      this.snapshot.addListener(this.listener);
    }
    this.refresh();
  }

  aboutToDisappear(): void {
    if (this.snapshot !== null) {
      this.snapshot.removeListener(this.listener);
    }
  }

  private refresh(): void {
    const queues = this.snapshot !== null ? this.snapshot.queues : null;
    if (queues === null) {
      return;
    }
    this.queued = queues.cacheQueued;
    this.running = queues.cacheRunning;
    this.ready = queues.cacheReady;
  }

  private static formatCount(value: number): string {
    return value > 99 ? '99+' : `${value}`;
  }

  @Builder
  countItem(icon: string, value: number, tint: ResourceColor) {
    Row({ space: 3 }) {
      SymbolGlyph($r(icon))
        .fontSize(13)
        .fontColor([tint])
      Text(CacheBadge.formatCount(value))
        .fontSize(11)
        .fontColor(tint)
        .fontWeight(FontWeight.Medium)
    }
    .padding({ left: 6, right: 6, top: 3, bottom: 3 })
    .backgroundColor($r('app.color.badge_bg'))
    .borderRadius(8)
  }

  build() {
    Row({ space: 6 }) {
      this.countItem('sys.symbol.clock', this.queued, '#667085')
      this.countItem('sys.symbol.video', this.running, '#B4233A')
      this.countItem('sys.symbol.checkmark', this.ready, '#12B76A')
    }
  }
}
