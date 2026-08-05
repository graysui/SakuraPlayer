/**
 * 女优详情页面（AC-051/052/076/077）。
 * - 资料头：头像（GfriendsImage）、显示名、中日文名（不重复）、别名换行、简介空态。
 * - 收藏按钮（在途防重、失败保留旧值）。
 * - 写真网格：单图失败占位隔离（不移除其他写真）；空图库独立空态。
 * - 关联影片：只读 MovieCard 网格（保持服务端顺序；点击 push MovieDetail 由 TASK-307 接管）。
 * - aboutToDisappear 注销 store listener（命名回调可注销）。
 */

import { display, mediaquery } from '@kit.ArkUI';
import { ActorDetailStatus, ActorDetailStore, actorsStore } from './ActorsStore';
import { ActorSummary, MovieSummary } from '../../core/api/ApiModels';
import { authStore } from '../../core/auth/AuthStore';
import { GfriendsImage } from '../../core/images/GfriendsImage';
import { MovieCard } from '../library/MovieCard';

class GalleryDataSource implements IDataSource {
  private items: string[] = [];
  private listeners: DataChangeListener[] = [];

  sync(items: string[]): void {
    this.items = items;
    for (const listener of this.listeners) {
      listener.onDataReloaded();
    }
  }

  totalCount(): number {
    return this.items.length;
  }

  getData(index: number): string {
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
export struct ActorDetailPage {
  @Require pathStack: NavPathStack;
  @Require actorId: string;
  @Require summary: ActorSummary;
  private store: ActorDetailStore = new ActorDetailStore((actorId: string, enabled: boolean) => {
    actorsStore.acceptFavorite(actorId, enabled);
  });
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  private readonly onActorsChanged: () => void = (): void => {
    // 列表收藏变化同步到当前详情（契约：成功后同步当前详情与已加载列表）
    const detail = this.store.detail;
    if (detail === null) {
      return;
    }
    const index = actorsStore.items.findIndex((item: ActorSummary) => item.id === detail.summary.id);
    if (index >= 0 && actorsStore.items[index].favorite !== detail.summary.favorite) {
      this.store.acceptFavorite(actorsStore.items[index].favorite);
    }
  };
  private gallerySource: GalleryDataSource = new GalleryDataSource();
  @State status: number = ActorDetailStatus.IDLE;
  @State displayName: string = '';
  @State nameZh: string | null = null;
  @State nameJa: string | null = null;
  @State aliases: string[] = [];
  @State bio: string | null = null;
  @State galleryCount: number = 0;
  @State movieItems: MovieSummary[] = [];
  @State favoriteErrorMessage: string | null = null;
  @State favorite: boolean = false;
  @State favoriteInFlight: boolean = false;
  @State galleryColumns: number = 3;
  @State errorMessage: string | null = null;
  private orientationListener: mediaquery.MediaQueryListener | null = null;

  aboutToAppear(): void {
    this.store.attach(authStore.apiClientProvider);
    this.store.addChangeListener(this.onStoreChanged);
    actorsStore.addChangeListener(this.onActorsChanged);
    // 先用列表摘要立即渲染资料头，详情加载后刷新
    this.displayName = this.summary.displayName;
    this.nameZh = this.summary.nameZh;
    this.nameJa = this.summary.nameJa;
    this.aliases = this.summary.aliases;
    this.favorite = this.summary.favorite;
    this.updateColumns();
    this.orientationListener = mediaquery.matchMediaSync('(orientation: landscape)');
    this.orientationListener.on('change', (result: mediaquery.MediaQueryResult) => {
      this.galleryColumns = result.matches ? 4 : 3;
    });
    if (this.store.status === ActorDetailStatus.IDLE) {
      this.store.load(this.actorId);
    }
  }

  aboutToDisappear(): void {
    this.store.removeChangeListener(this.onStoreChanged);
    actorsStore.removeChangeListener(this.onActorsChanged);
    if (this.orientationListener !== null) {
      this.orientationListener.off('change');
      this.orientationListener = null;
    }
    this.store.detach();
  }

  private syncFromStore(): void {
    const detail = this.store.detail;
    this.status = this.store.status;
    this.errorMessage = this.store.errorMessage;
    this.favoriteInFlight = this.store.favoriteInFlight;
    this.favoriteErrorMessage = this.store.favoriteErrorMessage;
    if (detail !== null) {
      this.displayName = detail.summary.displayName;
      this.nameZh = detail.summary.nameZh;
      this.nameJa = detail.summary.nameJa;
      this.aliases = detail.summary.aliases;
      this.bio = detail.bio;
      this.favorite = detail.summary.favorite;
      this.gallerySource.sync(detail.galleryUrls);
      this.galleryCount = detail.galleryUrls.length;
      this.movieItems = detail.movies;
    }
  }

  private updateColumns(): void {
    const widthVp = display.getDefaultDisplaySync().width / display.getDefaultDisplaySync().densityPixels;
    if (widthVp < 600) {
      this.galleryColumns = 3;
    } else if (widthVp < 840) {
      this.galleryColumns = 4;
    } else {
      this.galleryColumns = 5;
    }
  }

  private columnsTemplate(columns: number): string {
    let template = '';
    for (let i = 0; i < columns; i++) {
      template += template.length === 0 ? '1fr' : ' 1fr';
    }
    return template;
  }

  private namesLine(): string {
    const parts: string[] = [];
    if (this.nameZh !== null && this.nameZh.length > 0 && this.nameZh !== this.displayName) {
      parts.push(this.nameZh);
    }
    if (this.nameJa !== null && this.nameJa.length > 0 && this.nameJa !== this.displayName &&
      this.nameJa !== this.nameZh) {
      parts.push(this.nameJa);
    }
    return parts.join(' / ');
  }

  @Builder
  header() {
    Row({ space: 12 }) {
      GfriendsImage({ url: this.summary.profileUrl })
        .width(72)
        .height(96)
        .borderRadius(8)
      Column({ space: 4 }) {
        Row({ space: 8 }) {
          Text(this.displayName)
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor($r('app.color.text_primary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .layoutWeight(1)
          Text(this.favorite ? '★' : '☆')
            .fontSize(22)
            .fontColor(this.favorite ? '#F5B301' : $r('app.color.text_secondary'))
            .onClick(() => this.store.setFavorite(!this.favorite))
            .padding(4)
        }
        .width('100%')
        if (this.namesLine().length > 0) {
          Text(this.namesLine())
            .fontSize(12)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
        }
        if (this.aliases.length > 0) {
          Text(`别名：${this.aliases.join('、')}`)
            .fontSize(11)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(2)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
        }
      }
      .alignItems(HorizontalAlign.Start)
      .layoutWeight(1)
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12, bottom: 12 })
  }

  @Builder
  favoriteErrorBar() {
    if (this.favoriteErrorMessage !== null) {
      Text('收藏操作失败，请重试')
        .fontSize(12)
        .fontColor('#FF3B30')
        .width('100%')
        .padding({ left: 16, right: 16, top: 2, bottom: 2 })
    }
  }

  @Builder
  bioSection() {
    if (this.bio !== null && this.bio.length > 0) {
      Column({ space: 4 }) {
        Text('简介')
          .fontSize(13)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.text_primary'))
        Text(this.bio)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
      }
      .alignItems(HorizontalAlign.Start)
      .width('100%')
      .padding({ left: 16, right: 16, top: 4, bottom: 8 })
    }
  }

  @Builder
  gallerySection() {
    Column({ space: 6 }) {
      Text('写真')
        .fontSize(13)
        .fontWeight(FontWeight.Medium)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.galleryCount === 0) {
        Text('暂无写真')
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .padding({ top: 8, bottom: 8 })
      } else {
        Grid() {
          LazyForEach(this.gallerySource, (url: string, index: number) => {
            GridItem() {
              GfriendsImage({ url: url })
                .width('100%')
                .height(120)
                .borderRadius(6)
            }
          }, (url: string, index: number) => `${index}:${url}`)
        }
        .columnsTemplate(this.columnsTemplate(this.galleryColumns))
        .columnsGap(6)
        .rowsGap(6)
        .width('100%')
        .height(120 * Math.ceil(this.galleryCount / this.galleryColumns) +
          Math.max(0, Math.ceil(this.galleryCount / this.galleryColumns) - 1) * 6)
      }
    }
    .alignItems(HorizontalAlign.Start)
    .width('100%')
    .padding({ left: 16, right: 16, top: 4, bottom: 8 })
  }

  @Builder
  moviesSection() {
    if (this.movieItems.length > 0) {
      Column({ space: 6 }) {
        Text('关联影片')
          .fontSize(13)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.text_primary'))
          .width('100%')
        ForEach(this.movieItems, (movie: MovieSummary) => {
          MovieCard({ movie: movie })
            .onClick(() => {
              this.pathStack.pushPath({ name: 'MovieDetail', param: movie });
            })
            .margin({ bottom: 10 })
        }, (movie: MovieSummary) => movie.id)
      }
      .alignItems(HorizontalAlign.Start)
      .width('100%')
      .padding({ left: 12, right: 12, top: 4, bottom: 12 })
    }
  }

  @Builder
  statusArea() {
    Column({ space: 10 }) {
      if (this.status === ActorDetailStatus.LOADING) {
        LoadingProgress()
          .width(28)
          .height(28)
      } else if (this.status === ActorDetailStatus.FAILED) {
        Text(this.errorMessage ?? '详情加载失败')
          .fontSize(13)
          .fontColor('#FF3B30')
          .maxLines(2)
        Button('重试')
          .fontSize(13)
          .onClick(() => this.store.retry())
      } else {
        // 详情 READY 后信息区由 syncFromStore 渲染；此处不出现
      }
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  build() {
    Column() {
      if (this.status === ActorDetailStatus.READY) {
        Scroll() {
          Column() {
            this.header()
            this.favoriteErrorBar()
            this.bioSection()
            this.gallerySection()
            this.moviesSection()
          }
          .width('100%')
        }
        .layoutWeight(1)
        .scrollBar(BarState.Off)
        .align(Alignment.Top)
      } else if (this.status === ActorDetailStatus.IDLE || this.status === ActorDetailStatus.LOADING) {
        // 详情未就绪：先显示摘要资料头 + 加载指示
        Column() {
          this.header()
          LoadingProgress()
            .width(28)
            .height(28)
            .margin({ top: 40 })
        }
        .width('100%')
        .height('100%')
      } else {
        this.statusArea()
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.background'))
  }
}
