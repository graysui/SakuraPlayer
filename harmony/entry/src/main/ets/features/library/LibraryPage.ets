/**
 * 媒体库页面（AC-063/064/067/068/077）。
 * - 去重影片网格，LazyForEach 按 movie ID 稳定键控，@Reusable 卡片复用。
 * - 直屏/横屏响应式列数（if/else 切换，不用 Visibility 保留隐藏网格）。
 * - 六分类快捷栏 + 组合筛选 sheet + 游标分页（滚动到底加载更多）。
 * - 空/加载/失败/追加失败状态展示。
 */

import { display, mediaquery } from '@kit.ArkUI';
import { libraryStore, LibraryFilters, LibraryStatus } from './LibraryStore';
import { MovieSummary } from '../../core/api/ApiModels';
import { MovieCard } from './MovieCard';
import { LibraryFiltersSheet } from './LibraryFilters';

/** LazyForEach 数据源：封装 store 的影片数组，变化时全量通知重载。 */
class MovieDataSource implements IDataSource {
  private items: MovieSummary[] = [];
  private listeners: DataChangeListener[] = [];

  sync(items: MovieSummary[]): void {
    this.items = items;
    for (const listener of this.listeners) {
      listener.onDataReloaded();
    }
  }

  totalCount(): number {
    return this.items.length;
  }

  getData(index: number): MovieSummary {
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
export struct LibraryPage {
  @Require pathStack: NavPathStack;
  private dataSource: MovieDataSource = new MovieDataSource();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  @State gridColumns: number = 2;
  @State status: number = LibraryStatus.IDLE;
  @State itemsCount: number = 0;
  @State showFilters: boolean = false;
  private orientationListener: mediaquery.MediaQueryListener | null = null;

  aboutToAppear(): void {
    libraryStore.addChangeListener(this.onStoreChanged);
    this.updateColumns();
    this.syncFromStore();
    if (libraryStore.status === LibraryStatus.IDLE) {
      libraryStore.refresh();
    }
    // 横竖屏切换时更新列数（DoR：phone portrait/landscape breakpoint）
    this.orientationListener = mediaquery.matchMediaSync('(orientation: landscape)');
    this.orientationListener.on('change', (result: mediaquery.MediaQueryResult) => {
      this.gridColumns = result.matches ? 3 : 2;
    });
  }

  aboutToDisappear(): void {
    libraryStore.removeChangeListener(this.onStoreChanged);
    if (this.orientationListener !== null) {
      this.orientationListener.off('change');
      this.orientationListener = null;
    }
  }

  private syncFromStore(): void {
    this.dataSource.sync(libraryStore.items);
    this.status = libraryStore.status;
    this.itemsCount = libraryStore.items.length;
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

  @Builder
  categoryChip(category: string) {
    Text(category)
      .fontSize(12)
      .fontColor(libraryStore.categories.includes(category) ? '#FFFFFF' : $r('app.color.text_primary'))
      .padding({ left: 12, right: 12, top: 6, bottom: 6 })
      .backgroundColor(libraryStore.categories.includes(category) ? $r('app.color.primary') : $r('app.color.surface_alt'))
      .borderRadius(14)
      .onClick(() => libraryStore.toggleCategory(category))
  }

  @Builder
  categoryBar() {
    Scroll() {
      Row({ space: 8 }) {
        ForEach(LibraryFilters.CATEGORIES, (category: string) => {
          this.categoryChip(category)
        }, (category: string) => category)
      }
      .padding({ left: 16, right: 16 })
    }
    .scrollable(ScrollDirection.Horizontal)
    .scrollBar(BarState.Off)
    .width('100%')
    .height(40)
  }

  @Builder
  topBar() {
    Row({ space: 8 }) {
      Text('媒体库')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
      Blank()
      Text('筛选')
        .fontSize(13)
        .fontColor($r('app.color.primary'))
        .onClick(() => {
          this.showFilters = true;
        })
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 6, bottom: 6 })
  }

  @Builder
  statusArea() {
    Column({ space: 10 }) {
      if (this.status === LibraryStatus.LOADING || this.status === LibraryStatus.APPENDING) {
        LoadingProgress()
          .width(28)
          .height(28)
      } else if (this.status === LibraryStatus.FAILED) {
        Text(libraryStore.errorMessage ?? '媒体库加载失败')
          .fontSize(13)
          .fontColor('#FF3B30')
          .maxLines(2)
        Button('重试')
          .fontSize(13)
          .onClick(() => libraryStore.refresh())
      } else if (this.status === LibraryStatus.INVALID) {
        Text(libraryStore.errorMessage ?? '请修正筛选条件')
          .fontSize(13)
          .fontColor('#FF3B30')
      } else {
        Text('没有符合筛选条件的影片')
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
      }
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .layoutWeight(1)
  }

  @Builder
  gridArea() {
    Grid() {
      LazyForEach(this.dataSource, (item: MovieSummary) => {
        GridItem() {
          MovieCard({ movie: item })
            .onClick(() => {
              this.pathStack.pushPath({ name: 'MovieDetail', param: item });
            })
        }
      }, (item: MovieSummary) => item.id)
    }
    .columnsTemplate(this.columnsTemplate())
    .columnsGap(10)
    .rowsGap(10)
    .padding({ left: 12, right: 12, top: 4, bottom: 12 })
    .onReachEnd(() => {
      libraryStore.loadMore();
    })
    .layoutWeight(1)
  }

  @Builder
  appendErrorBar() {
    if (this.status === LibraryStatus.APPEND_FAILED) {
      Row({ space: 8 }) {
        Text('加载更多失败')
          .fontSize(12)
          .fontColor('#FF3B30')
        Text('重试')
          .fontSize(12)
          .fontColor($r('app.color.primary'))
          .onClick(() => libraryStore.retryAppend())
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .padding(8)
    } else if (this.status === LibraryStatus.FAILED && this.itemsCount > 0) {
      Row({ space: 8 }) {
        Text('刷新失败，当前显示旧数据')
          .fontSize(12)
          .fontColor('#FF3B30')
        Text('重试')
          .fontSize(12)
          .fontColor($r('app.color.primary'))
          .onClick(() => libraryStore.refresh())
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .padding(8)
    }
  }

  @Builder
  filtersSheet() {
    LibraryFiltersSheet({
      onDismiss: (): void => {
        this.showFilters = false;
      },
    })
  }

  build() {
    Column() {
      this.topBar()
      this.categoryBar()
      if (this.status === LibraryStatus.READY && this.itemsCount === 0) {
        this.statusArea()
      } else if (this.status === LibraryStatus.FAILED && this.itemsCount === 0) {
        this.statusArea()
      } else if (this.status === LibraryStatus.INVALID) {
        this.statusArea()
      } else {
        this.gridArea()
        this.appendErrorBar()
        if (this.status === LibraryStatus.LOADING && this.itemsCount === 0) {
          this.statusArea()
        }
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.background'))
    .bindSheet($$this.showFilters, this.filtersSheet(), {
      height: SheetSize.LARGE,
      detents: [SheetSize.MEDIUM, SheetSize.LARGE],
      showClose: true,
      title: { title: '组合筛选' },
    })
  }
}
