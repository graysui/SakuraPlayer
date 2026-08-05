/**
 * 女优列表页面（AC-051/052/075/077）。
 * - 姓名/别名搜索（300ms 防抖 + 回车立即提交）+ 普通/收藏 segmented。
 * - 女优卡：头像（GfriendsImage）、显示名、中日文名、别名、收藏按钮。
 * - 竖屏 2 列/横屏 3 列响应式网格；空/加载/失败/追加失败状态互不冒充。
 * - 点击卡片进入详情（push ActorDetail）。
 */

import { display, mediaquery } from '@kit.ArkUI';
import { actorsStore, ActorsStatus } from './ActorsStore';
import { ActorSummary } from '../../core/api/ApiModels';
import { GfriendsImage } from '../../core/images/GfriendsImage';

/** LazyForEach 数据源：封装 store 的女优数组，变化时全量通知重载。 */
class ActorDataSource implements IDataSource {
  private items: ActorSummary[] = [];
  private listeners: DataChangeListener[] = [];

  sync(items: ActorSummary[]): void {
    this.items = items;
    for (const listener of this.listeners) {
      listener.onDataReloaded();
    }
  }

  totalCount(): number {
    return this.items.length;
  }

  getData(index: number): ActorSummary {
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
export struct ActorsPage {
  @Require pathStack: NavPathStack;
  private dataSource: ActorDataSource = new ActorDataSource();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  private lastSyncedItems: ActorSummary[] = [];
  @State gridColumns: number = 2;
  @State status: number = ActorsStatus.IDLE;
  @State itemsCount: number = 0;
  @State query: string = '';
  @State favoriteMode: boolean = false;
  @State refreshing: boolean = false;
  @State favoriteErrorMessage: string | null = null;
  private orientationListener: mediaquery.MediaQueryListener | null = null;

  aboutToAppear(): void {
    actorsStore.addChangeListener(this.onStoreChanged);
    this.updateColumns();
    this.syncFromStore();
    if (actorsStore.status === ActorsStatus.IDLE) {
      actorsStore.refresh();
    }
    this.orientationListener = mediaquery.matchMediaSync('(orientation: landscape)');
    this.orientationListener.on('change', (result: mediaquery.MediaQueryResult) => {
      this.gridColumns = result.matches ? 3 : 2;
    });
  }

  aboutToDisappear(): void {
    actorsStore.removeChangeListener(this.onStoreChanged);
    actorsStore.cancelPendingQuery();
    if (this.orientationListener !== null) {
      this.orientationListener.off('change');
      this.orientationListener = null;
    }
  }

  private syncFromStore(): void {
    // 只有 items 引用变化才重建网格（防抖输入期间不闪跳）
    if (actorsStore.items !== this.lastSyncedItems) {
      this.lastSyncedItems = actorsStore.items;
      this.dataSource.sync(actorsStore.items);
    }
    this.status = actorsStore.status;
    this.itemsCount = actorsStore.items.length;
    this.query = actorsStore.query;
    this.favoriteMode = actorsStore.favoriteMode;
    this.refreshing = actorsStore.refreshing;
    this.favoriteErrorMessage = actorsStore.favoriteErrorMessage;
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
  searchBar() {
    Row({ space: 8 }) {
      TextInput({ placeholder: '搜索姓名或别名', text: this.query })
        .layoutWeight(1)
        .fontSize(13)
        .height(36)
        .onChange((value: string) => {
          actorsStore.setQuery(value);
        })
        .onSubmit(() => {
          actorsStore.submitQuery();
        })
      Button(this.favoriteMode ? '全部' : '收藏')
        .fontSize(12)
        .height(36)
        .backgroundColor(this.favoriteMode ? $r('app.color.primary') : $r('app.color.surface_alt'))
        .fontColor(this.favoriteMode ? '#FFFFFF' : $r('app.color.text_primary'))
        .onClick(() => actorsStore.toggleFavoriteMode())
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 8, bottom: 4 })
  }

  @Builder
  refreshErrorBar() {
    if (this.favoriteErrorMessage !== null) {
      Row({ space: 8 }) {
        Text('收藏操作失败，请重试')
          .fontSize(12)
          .fontColor('#FF3B30')
          .maxLines(1)
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .padding(6)
    } else if ((this.status === ActorsStatus.READY || this.status === ActorsStatus.FAILED) &&
      this.itemsCount > 0 && actorsStore.errorMessage !== null) {
      Row({ space: 8 }) {
        Text('刷新失败，当前显示旧数据')
          .fontSize(12)
          .fontColor('#FF3B30')
          .maxLines(1)
        Text('重试')
          .fontSize(12)
          .fontColor($r('app.color.primary'))
          .onClick(() => actorsStore.refresh())
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .padding(6)
    }
  }

  @Builder
  actorCard(item: ActorSummary) {
    Column({ space: 0 }) {
      // 头像区（GfriendsImage：占位/加载/失败统一）
      GfriendsImage({ url: item.profileUrl })
        .width('100%')
        .height(150)
      // 信息区
      Column({ space: 2 }) {
        Row() {
          Text(item.displayName)
            .fontSize(13)
            .fontWeight(FontWeight.Medium)
            .fontColor($r('app.color.text_primary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .layoutWeight(1)
          Text(item.favorite ? '★' : '☆')
            .fontSize(14)
            .fontColor(item.favorite ? '#F5B301' : $r('app.color.text_secondary'))
            .onClick(() => actorsStore.setFavorite(item.id, !item.favorite))
            .padding(4)
        }
        .width('100%')
        if (item.nameZh !== null && item.nameZh !== item.displayName) {
          Text(item.nameZh)
            .fontSize(11)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .width('100%')
        }
        Text(this.aliasesText(item))
          .fontSize(10)
          .fontColor($r('app.color.text_secondary'))
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .width('100%')
      }
      .alignItems(HorizontalAlign.Start)
      .width('100%')
      .padding(8)
    }
    .width('100%')
    .backgroundColor($r('app.color.surface'))
    .borderRadius(10)
    .border({ width: 0.5, color: $r('app.color.divider') })
    .clip(true)
    .onClick(() => {
      this.pathStack.pushPath({ name: 'ActorDetail', param: item });
    })
  }

  private aliasesText(item: ActorSummary): string {
    return item.aliases.length > 0 ? `别名：${item.aliases.join('、')}` : '';
  }

  @Builder
  statusArea() {
    Column({ space: 10 }) {
      if (this.status === ActorsStatus.LOADING || this.status === ActorsStatus.APPENDING) {
        LoadingProgress()
          .width(28)
          .height(28)
      } else if (this.status === ActorsStatus.FAILED) {
        Text(actorsStore.errorMessage ?? '女优列表加载失败')
          .fontSize(13)
          .fontColor('#FF3B30')
          .maxLines(2)
        Button('重试')
          .fontSize(13)
          .onClick(() => actorsStore.retryInitial())
      } else {
        Text(this.favoriteMode ? '收藏列表暂无女优' : '暂无女优')
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
      LazyForEach(this.dataSource, (item: ActorSummary) => {
        GridItem() {
          this.actorCard(item)
        }
      }, (item: ActorSummary) => item.id)
    }
    .columnsTemplate(this.columnsTemplate())
    .columnsGap(10)
    .rowsGap(10)
    .padding({ left: 12, right: 12, top: 4, bottom: 12 })
    .onReachEnd(() => {
      actorsStore.loadMore();
    })
    .layoutWeight(1)
  }

  @Builder
  appendErrorBar() {
    if (this.status === ActorsStatus.APPEND_FAILED) {
      Row({ space: 8 }) {
        Text('加载更多失败')
          .fontSize(12)
          .fontColor('#FF3B30')
        Text('重试')
          .fontSize(12)
          .fontColor($r('app.color.primary'))
          .onClick(() => actorsStore.retryAppend())
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .padding(8)
    } else if (this.status === ActorsStatus.APPENDING) {
      LoadingProgress()
        .width(20)
        .height(20)
        .margin({ top: 6, bottom: 6 })
    }
  }

  @Builder
  contentArea() {
    if (this.status === ActorsStatus.IDLE || this.status === ActorsStatus.LOADING) {
      this.statusArea()
    } else if (this.status === ActorsStatus.READY && this.itemsCount === 0) {
      this.statusArea()
    } else if (this.status === ActorsStatus.FAILED && this.itemsCount === 0) {
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
      this.searchBar()
      this.refreshErrorBar()
      Refresh({ refreshing: $$this.refreshing }) {
        this.contentArea()
      }
      .onRefreshing(() => {
        actorsStore.refresh();
      })
      .layoutWeight(1)
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.background'))
  }
}
