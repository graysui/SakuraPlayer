/**
 * 排行榜页面（AC-046/069-073）。
 * - segmented 四榜单（日/周/月/TOP250）；TOP250 年份 Select（总榜 + 服务端 available_years）。
 * - Refresh 下拉刷新只调用后端快照 API，不触发客户端 JavDB 抓取。
 * - rank 角标 + MovieCard 复用；竖屏 2 列/横屏 3 列响应式网格（LazyForEach 按 movie ID 键控）。
 * - 空/加载/失败/不可用/追加失败状态互不冒充；synced_at 显示本地可读快照时间。
 */

import { display, mediaquery } from '@kit.ArkUI';
import { rankingsStore, RankingsStore, RankingsStatus } from './RankingsStore';
import { RankingItem } from '../../core/api/ApiModels';
import { MovieCard } from '../library/MovieCard';

/** LazyForEach 数据源：封装 store 的榜单数组，变化时全量通知重载。 */
class RankingDataSource implements IDataSource {
  private items: RankingItem[] = [];
  private listeners: DataChangeListener[] = [];

  sync(items: RankingItem[]): void {
    this.items = items;
    for (const listener of this.listeners) {
      listener.onDataReloaded();
    }
  }

  totalCount(): number {
    return this.items.length;
  }

  getData(index: number): RankingItem {
    return this.items[index];
  }

  registerDataChangeListener(listener: DataChangeListener): void {
    if (!this.listeners.includes(listener)) {
      this.listeners.push(listener);
    }
  }

  unregisterDataChangeListener(listener: DataChangeListener): void {
    const index = this.listeners.indexOf(listener);
    if (index >= 0) {
      this.listeners.splice(index, 1);
    }
  }
}

@Component
export struct RankingsPage {
  @Require pathStack: NavPathStack;
  private dataSource: RankingDataSource = new RankingDataSource();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  @State gridColumns: number = 2;
  @State status: number = RankingsStatus.IDLE;
  @State itemsCount: number = 0;
  @State refreshing: boolean = false;
  @State syncedAt: string | null = null;
  @State availableYears: number[] = [];
  @State board: string = 'daily';
  @State year: number | null = null;
  @State unavailableReason: string | null = null;
  @State showYearSelect: boolean = false;
  private orientationListener: mediaquery.MediaQueryListener | null = null;

  aboutToAppear(): void {
    rankingsStore.addChangeListener(this.onStoreChanged);
    this.updateColumns();
    this.syncFromStore();
    if (rankingsStore.status === RankingsStatus.IDLE) {
      rankingsStore.refresh();
    }
    // 横竖屏切换时更新列数
    this.orientationListener = mediaquery.matchMediaSync('(orientation: landscape)');
    this.orientationListener.on('change', (result: mediaquery.MediaQueryResult) => {
      this.gridColumns = result.matches ? 3 : 2;
    });
  }

  aboutToDisappear(): void {
    rankingsStore.removeChangeListener(this.onStoreChanged);
    if (this.orientationListener !== null) {
      this.orientationListener.off('change');
      this.orientationListener = null;
    }
  }

  private syncFromStore(): void {
    this.dataSource.sync(rankingsStore.items);
    this.status = rankingsStore.status;
    this.itemsCount = rankingsStore.items.length;
    this.refreshing = rankingsStore.refreshing;
    this.syncedAt = rankingsStore.syncedAt;
    this.availableYears = rankingsStore.availableYears;
    this.board = rankingsStore.board;
    this.year = rankingsStore.year;
    this.unavailableReason = rankingsStore.unavailableReason;
    this.showYearSelect = rankingsStore.board === 'top250' && rankingsStore.availableYears.length > 0;
  }

  /** 响应式列数：phone portrait 2 列、landscape/小平板 3 列、大屏 4 列。 */
  private updateColumns(): void {
    const widthVp = display.getDefaultDisplaySync().width / display.getDefaultDisplaySync().densityPixels;
    if (widthVp < 600) {
      this.gridColumns = 2;
    } else if (widthVp < 840) {
      this.gridColumns = 3;
    } else {
      this.gridColumns = 4;
    }
  }

  private columnsTemplate(): string {
    let template = '';
    for (let i = 0; i < this.gridColumns; i++) {
      template += template.length === 0 ? '1fr' : ' 1fr';
    }
    return template;
  }

  private boardTitle(board: string): string {
    if (board === 'weekly') {
      return '周榜';
    }
    if (board === 'monthly') {
      return '月榜';
    }
    if (board === 'top250') {
      return 'TOP250';
    }
    return '日榜';
  }

  private yearOptions(): SelectOption[] {
    const options: SelectOption[] = [{ value: '总榜' }];
    for (const year of this.availableYears) {
      options.push({ value: `${year}` });
    }
    return options;
  }

  private selectedYearIndex(): number {
    if (this.year === null) {
      return 0;
    }
    const index = this.availableYears.indexOf(this.year);
    return index < 0 ? 0 : index + 1;
  }

  private yearDisplay(): string {
    return this.year === null ? '总榜' : `${this.year}`;
  }

  private formatSyncedAt(raw: string): string {
    try {
      const ms = Date.parse(raw);
      if (Number.isNaN(ms)) {
        return raw;
      }
      const date = new Date(ms);
      const pad = (v: number): string => (v < 10 ? `0${v}` : `${v}`);
      return `更新于 ${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
        `${pad(date.getHours())}:${pad(date.getMinutes())}`;
    } catch (e) {
      return raw;
    }
  }

  private unavailableTitle(): string {
    if (this.unavailableReason === 'credentials_not_configured') {
      return 'TOP250 尚未配置 JavDB 凭据，暂无可用的榜单快照';
    }
    if (this.unavailableReason === 'credentials_invalid') {
      return 'JavDB 凭据已失效，暂无可用的榜单快照';
    }
    if (this.unavailableReason === 'never_synced') {
      return '当前榜单尚未生成快照';
    }
    if (this.unavailableReason === 'sync_failed') {
      return '当前榜单最近同步失败，且没有可用快照';
    }
    return '当前榜单暂无快照';
  }

  @Builder
  boardBar() {
    Row({ space: 6 }) {
      ForEach(RankingsStore.BOARDS, (board: string) => {
        Text(this.boardTitle(board))
          .fontSize(13)
          .fontWeight(this.board === board ? FontWeight.Medium : FontWeight.Normal)
          .fontColor(this.board === board ? '#FFFFFF' : $r('app.color.text_primary'))
          .textAlign(TextAlign.Center)
          .height(32)
          .layoutWeight(1)
          .backgroundColor(this.board === board ? $r('app.color.primary') : $r('app.color.surface_alt'))
          .borderRadius(16)
          .onClick(() => rankingsStore.selectBoard(board))
      }, (board: string) => board)
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 8, bottom: 4 })
  }

  @Builder
  metaRow() {
    Row({ space: 8 }) {
      if (this.showYearSelect) {
        Select(this.yearOptions())
          .selected(this.selectedYearIndex())
          .value(this.yearDisplay())
          .font({ size: 13 })
          .width(120)
          .onSelect((index: number) => {
            if (index === 0) {
              rankingsStore.selectYear(null);
              return;
            }
            const year = this.availableYears[index - 1];
            if (year !== undefined) {
              rankingsStore.selectYear(year);
            }
          })
      }
      Blank()
      if (this.syncedAt !== null) {
        Text(this.formatSyncedAt(this.syncedAt))
          .fontSize(11)
          .fontColor($r('app.color.text_secondary'))
          .maxLines(1)
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 2, bottom: 2 })
  }

  @Builder
  refreshErrorBar() {
    if ((this.status === RankingsStatus.READY || this.status === RankingsStatus.FAILED) &&
      this.itemsCount > 0 && rankingsStore.errorMessage !== null) {
      Row({ space: 8 }) {
        Text('刷新失败，当前显示旧数据')
          .fontSize(12)
          .fontColor('#FF3B30')
          .maxLines(1)
        Text('重试')
          .fontSize(12)
          .fontColor($r('app.color.primary'))
          .onClick(() => rankingsStore.refresh())
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .padding(6)
    }
  }

  @Builder
  statusArea() {
    Column({ space: 10 }) {
      if (this.status === RankingsStatus.LOADING || this.status === RankingsStatus.APPENDING) {
        LoadingProgress()
          .width(28)
          .height(28)
      } else if (this.status === RankingsStatus.FAILED) {
        Text(rankingsStore.errorMessage ?? '排行榜加载失败')
          .fontSize(13)
          .fontColor('#FF3B30')
          .maxLines(2)
        Button('重试')
          .fontSize(13)
          .onClick(() => rankingsStore.retryInitial())
      } else if (this.status === RankingsStatus.UNAVAILABLE) {
        Text(this.unavailableTitle())
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
          .textAlign(TextAlign.Center)
          .maxLines(3)
        Button('重新加载')
          .fontSize(13)
          .onClick(() => rankingsStore.retryInitial())
      } else {
        Text('该榜单暂无影片')
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
      }
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  @Builder
  gridArea() {
    Grid() {
      LazyForEach(this.dataSource, (item: RankingItem) => {
        GridItem() {
          Stack({ alignContent: Alignment.TopStart }) {
            MovieCard({ movie: item.movie })
              .onClick(() => {
                this.pathStack.pushPath({ name: 'MovieDetail', param: item.movie });
              })
            Text(`${item.rank}`)
              .fontSize(10)
              .fontWeight(FontWeight.Bold)
              .fontColor('#FFFFFF')
              .width(24)
              .height(24)
              .textAlign(TextAlign.Center)
              .backgroundColor($r('app.color.primary'))
              .borderRadius(12)
              .margin({ left: 6, top: 6 })
          }
          .width('100%')
        }
      }, (item: RankingItem) => item.movie.id)
    }
    .columnsTemplate(this.columnsTemplate())
    .columnsGap(10)
    .rowsGap(10)
    .padding({ left: 12, right: 12, top: 4, bottom: 12 })
    .onReachEnd(() => {
      rankingsStore.loadMore();
    })
    .layoutWeight(1)
  }

  @Builder
  appendErrorBar() {
    if (this.status === RankingsStatus.APPEND_FAILED) {
      Row({ space: 8 }) {
        Text('加载更多失败')
          .fontSize(12)
          .fontColor('#FF3B30')
        Text('重试')
          .fontSize(12)
          .fontColor($r('app.color.primary'))
          .onClick(() => rankingsStore.retryAppend())
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .padding(8)
    }
  }

  @Builder
  contentArea() {
    if (this.status === RankingsStatus.READY && this.itemsCount === 0) {
      this.statusArea()
    } else if (this.status === RankingsStatus.FAILED && this.itemsCount === 0) {
      this.statusArea()
    } else if (this.status === RankingsStatus.UNAVAILABLE) {
      this.statusArea()
    } else if (this.status === RankingsStatus.LOADING && this.itemsCount === 0) {
      this.statusArea()
    } else {
      Column() {
        this.gridArea()
        this.appendErrorBar()
      }
      .width('100%')
      .height('100%')
    }
  }

  build() {
    Column() {
      this.boardBar()
      this.metaRow()
      this.refreshErrorBar()
      Refresh({ refreshing: $$this.refreshing }) {
        this.contentArea()
      }
      .onRefreshing(() => {
        rankingsStore.refresh();
      })
      .layoutWeight(1)
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.background'))
  }
}
