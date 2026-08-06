/**
 * 影片详情页面（AC-031/033/034/035/068/074/077/078）。
 *
 * - 连续滚动单面：资料头（封面/番号/中日标题/日期/厂商/系列/导演/评分/标签/演员/收藏/播放）
 *   → 受限资料状态 → 来源 → 简介 → 剧照。
 * - 来源选择用 UIContext.openBindSheet（非 deprecated API）；选择只产生 source_id，
 *   选择行不访问网络；rejected 不可选；重载后来源消失自动清空选择。
 * - 收藏：受限详情不显示；在途防重；失败保留旧值并显示非阻断提示。
 * - 播放按钮：未选来源禁用但保持几何稳定；文案跟随影片级进度（播放/继续播放 N%/已看完）。
 * - 失败态：resource_not_found → “影片资料不存在”（可返回，不重试）；其他 → 重试。
 * - 演员项只按 ActorSummary id 导航；长标题/标签/别名换行不遮操作。
 */

import { display, mediaquery } from '@kit.ArkUI';
import { ComponentContent } from '@kit.ArkUI';
import { MovieDetailStatus, MovieDetailStore } from './MovieDetailStore';
import { ActorSummary, MovieDetail, MovieSource, MovieSummary, PlaybackProgress } from '../../core/api/ApiModels';
import { authStore } from '../../core/auth/AuthStore';
import { CatalogImage } from './CatalogImage';
import { SourceDisplay, SourceSheetBuilder, SourceSheetParams } from './SourceSheet';

@Component
export struct MovieDetailPage {
  @Require pathStack: NavPathStack;
  @Require movieId: string;
  summary: MovieSummary | null = null;
  private store: MovieDetailStore = new MovieDetailStore();
  private readonly onStoreChanged: () => void = (): void => this.syncFromStore();
  private orientationListener: mediaquery.MediaQueryListener | null = null;
  private sheetContent: ComponentContent<SourceSheetParams> | null = null;

  // 显示状态（响应式）
  @State number: string = '';
  @State title: string = '';
  @State titleOriginal: string | null = null;
  @State coverUrl: string | null = null;
  @State releaseDate: string | null = null;
  @State publishDate: string | null = null;
  @State maker: string | null = null;
  @State series: string | null = null;
  @State director: string | null = null;
  @State score: number | null = null;
  @State tags: string[] = [];
  @State actors: ActorSummary[] = [];
  @State description: string | null = null;
  @State descriptionOriginal: string | null = null;
  @State sources: MovieSource[] = [];
  @State sourceCount: number = 0;
  @State selectedSourceId: string | null = null;
  @State favorite: boolean = false;
  @State favoriteInFlight: boolean = false;
  @State favoriteError: boolean = false;
  @State isLimited: boolean = false;
  @State metadataState: string = 'core_ready';
  @State metadataErrorCode: string | null = null;
  @State progress: PlaybackProgress | null = null;
  @State plotUrls: string[] = [];
  @State plotColumns: number = 3;

  aboutToAppear(): void {
    this.store.attach(authStore.apiClientProvider);
    this.store.addChangeListener(this.onStoreChanged);
    // 先用列表摘要立即渲染，详情加载后刷新
    if (this.summary !== null) {
      this.number = this.summary.number;
      this.title = this.summary.title;
      this.titleOriginal = this.summary.titleOriginal;
      this.coverUrl = this.summary.coverUrl;
      this.favorite = this.summary.favorite;
    }
    this.updatePlotColumns();
    this.orientationListener = mediaquery.matchMediaSync('(orientation: landscape)');
    this.orientationListener.on('change', (result: mediaquery.MediaQueryResult) => {
      this.plotColumns = result.matches ? 4 : 3;
    });
    if (this.store.status === MovieDetailStatus.IDLE) {
      this.store.load(this.movieId);
    }
  }

  aboutToDisappear(): void {
    this.store.removeChangeListener(this.onStoreChanged);
    this.store.detach();
    if (this.orientationListener !== null) {
      this.orientationListener.off('change');
      this.orientationListener = null;
    }
    this.closeSheet();
  }

  private updatePlotColumns(): void {
    const widthVp = display.getDefaultDisplaySync().width / display.getDefaultDisplaySync().densityPixels;
    this.plotColumns = widthVp < 600 ? 2 : 3;
  }

  private syncFromStore(): void {
    const detail = this.store.detail;
    if (detail !== null) {
      this.number = detail.number;
      this.title = detail.title;
      this.titleOriginal = detail.titleOriginal;
      this.coverUrl = detail.coverUrl;
      this.releaseDate = detail.releaseDate;
      this.publishDate = detail.publishDate;
      this.maker = detail.maker;
      this.series = detail.series;
      this.director = detail.director;
      this.score = detail.score;
      this.tags = detail.tags;
      this.actors = detail.actors;
      this.description = detail.description;
      this.descriptionOriginal = detail.descriptionOriginal;
      this.sources = detail.sources;
      this.sourceCount = detail.sourceCount;
      this.selectedSourceId = this.store.selectedSourceId;
      this.favorite = detail.favorite;
      this.isLimited = detail.isLimited();
      this.metadataState = detail.metadataState;
      this.metadataErrorCode = detail.metadataErrorCode;
      this.progress = detail.progress;
      this.plotUrls = detail.plotImageUrls;
    }
    this.favoriteInFlight = this.store.favoriteInFlight;
    this.favoriteError = this.store.favoriteError !== null;
  }

  private progressLabel(): string {
    const progress = this.progress;
    if (progress === null) {
      return '播放';
    }
    if (progress.completed) {
      return '已看完';
    }
    const fraction = progress.fraction();
    if (fraction !== null) {
      return `继续播放 ${Math.round(fraction * 100)}%`;
    }
    return `已播放 ${this.formatPosition(progress.positionSeconds)}`;
  }

  private formatPosition(seconds: number): string {
    const total = Math.max(0, Math.floor(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const two = (v: number): string => (v < 10 ? `0${v}` : `${v}`);
    if (h > 0) {
      return `${h}:${two(m)}:${two(s)}`;
    }
    return `${m}:${two(s)}`;
  }

  private displayDate(): string {
    const value = this.releaseDate !== null ? this.releaseDate : this.publishDate;
    return value === null ? '未知' : value;
  }

  /** 中日标题只有在不同时才单独显示。 */
  private showOriginalTitle(): boolean {
    const original = this.titleOriginal;
    if (original === null || original.trim().length === 0) {
      return false;
    }
    return original.trim() !== this.title.trim();
  }

  private toggleFavorite(): void {
    if (this.isLimited || this.favoriteInFlight) {
      return;
    }
    this.store.setFavorite(!this.favorite);
  }

  private openSourceSheet(): void {
    if (this.store.detail === null) {
      return;
    }
    this.closeSheet();
    const uiContext = this.getUIContext();
    const params: SourceSheetParams = {
      sources: this.sources,
      selectedSourceId: this.selectedSourceId,
      onSelect: (sourceId: string): void => {
        this.store.selectSource(sourceId);
        // 以 store 校验结果为准（来源瞬时失效时不显示未确认选择）
        this.selectedSourceId = this.store.selectedSourceId;
        this.closeSheet();
      },
    };
    this.sheetContent = new ComponentContent(uiContext, wrapBuilder(SourceSheetBuilder), params);
    uiContext.openBindSheet(this.sheetContent, {
      title: { title: `选择来源（${this.sourceCount}）` },
      height: SheetSize.MEDIUM,
      detents: [SheetSize.MEDIUM, SheetSize.LARGE],
      preferType: SheetType.BOTTOM,
    }).catch(() => {
      // sheet 打开失败：保持页面可用
    });
  }

  private closeSheet(): void {
    const content = this.sheetContent;
    if (content === null) {
      return;
    }
    this.sheetContent = null;
    const uiContext = this.getUIContext();
    uiContext.closeBindSheet(content).then(() => {
      content.dispose();
    }).catch(() => {
      // 已关闭：直接释放
      content.dispose();
    });
  }

  private metadataStatusText(): string {
    if (this.metadataState === 'queued') {
      return '资料排队中';
    }
    if (this.metadataState === 'running') {
      return '正在补全资料';
    }
    if (this.metadataState === 'failed') {
      return '资料补全失败';
    }
    return '';
  }

  private metadataErrorText(): string {
    if (this.metadataErrorCode === 'javdb_movie_not_found') {
      return 'JavDB 未找到该番号';
    }
    if (this.metadataErrorCode === 'metadata_timeout') {
      return '元数据刮削超时';
    }
    return '请在诊断页查看失败原因';
  }

  @Builder
  metadataStatusBar() {
    if (this.isLimited) {
      Row({ space: 6 }) {
        Text(this.metadataStatusText())
          .fontSize(13)
          .fontColor(this.metadataState === 'failed' ? '#FF3B30' : $r('app.color.text_secondary'))
        if (this.metadataState === 'failed') {
          Text(this.metadataErrorText())
            .fontSize(12)
            .fontColor('#FF3B30')
        }
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 10, bottom: 10 })
      .backgroundColor($r('app.color.surface_alt'))
    }
  }

  @Builder
  headerBlock() {
    Row({ space: 12 }) {
      // 封面 2:3
      Stack() {
        if (this.coverUrl !== null) {
          CatalogImage({ url: this.coverUrl })
        } else {
          Column() {
            SymbolGlyph($r('sys.symbol.doc'))
              .fontSize(40)
              .fontColor([$r('app.color.text_secondary')])
          }
          .justifyContent(FlexAlign.Center)
          .width('100%')
          .height('100%')
          .backgroundColor($r('app.color.surface_alt'))
        }
      }
      .width(130)
      .height(195)
      .borderRadius(6)
      .clip(true)
      Column({ space: 4 }) {
        Text(this.number)
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.text_primary'))
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .width('100%')
        Text(this.title)
          .fontSize(16)
          .fontWeight(FontWeight.Bold)
          .fontColor($r('app.color.text_primary'))
          .maxLines(3)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .width('100%')
        if (this.showOriginalTitle()) {
          Text(this.titleOriginal)
            .fontSize(13)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(2)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .width('100%')
        }
        Text(`日期：${this.displayDate()}`)
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .width('100%')
        if (this.maker !== null) {
          Text(`厂商：${this.maker}`)
            .fontSize(12)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .width('100%')
        }
        if (this.series !== null) {
          Text(`系列：${this.series}`)
            .fontSize(12)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .width('100%')
        }
        if (this.director !== null) {
          Text(`导演：${this.director}`)
            .fontSize(12)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .width('100%')
        }
        if (this.score !== null) {
          Text(`评分：${this.score}`)
            .fontSize(12)
            .fontColor($r('app.color.text_secondary'))
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .width('100%')
        }
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 16 })

    // 标签（自然换行）
    Row() {
      if (this.tags.length === 0) {
        Text('暂无标签')
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
      } else {
        Flex({ wrap: FlexWrap.Wrap }) {
          ForEach(this.tags, (tag: string) => {
            Text(tag)
              .fontSize(11)
              .fontColor($r('app.color.text_secondary'))
              .padding({ left: 8, right: 8, top: 3, bottom: 3 })
              .backgroundColor($r('app.color.surface_alt'))
              .borderRadius(12)
              .margin({ right: 6, bottom: 6 })
          }, (tag: string) => tag)
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 10 })

    // 演员（可换行导航项）
    Row() {
      if (this.actors.length === 0) {
        Text('暂无演员')
          .fontSize(12)
          .fontColor($r('app.color.text_secondary'))
      } else {
        Flex({ wrap: FlexWrap.Wrap }) {
          ForEach(this.actors, (actor: ActorSummary) => {
            Text(actor.displayName)
              .fontSize(13)
              .fontColor($r('app.color.primary'))
              .padding({ left: 10, right: 10, top: 5, bottom: 5 })
              .borderRadius(14)
              .border({ width: 0.5, color: $r('app.color.primary') })
              .margin({ right: 6, bottom: 6 })
              .onClick(() => {
                this.pathStack.pushPath({ name: 'ActorDetail', param: actor });
              })
          }, (actor: ActorSummary) => actor.id)
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 10 })

    // 操作区：收藏 + 播放
    Row({ space: 12 }) {
      if (!this.isLimited) {
        Button(this.favorite ? '★ 已收藏' : '☆ 收藏')
          .fontSize(14)
          .backgroundColor(this.favorite ? '#FF9F0A' : $r('app.color.surface_alt'))
          .fontColor(this.favorite ? '#FFFFFF' : $r('app.color.text_primary'))
          .height(44)
          .layoutWeight(1)
          .enabled(!this.favoriteInFlight)
          .onClick(() => this.toggleFavorite())
      }
      Button(this.progressLabel())
        .fontSize(14)
        .fontColor('#FFFFFF')
        .backgroundColor($r('app.color.primary'))
        .height(44)
        .layoutWeight(1)
        .opacity(this.selectedSourceId !== null ? 1 : 0.5)
        .enabled(this.selectedSourceId !== null)
        .onClick(() => {
          // 本任务只输出 source_id（store.selectedSourceId）；播放由后续任务消费
        })
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12, bottom: 4 })
    if (this.favoriteError) {
      Text('收藏更新失败，请重试')
        .fontSize(12)
        .fontColor('#FF3B30')
        .width('100%')
        .padding({ left: 16, right: 16, top: 2 })
    }
  }

  @Builder
  sourceBlock() {
    Column({ space: 8 }) {
      Text(`来源（${this.sourceCount}）`)
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      Row() {
        if (this.sources.length === 0) {
          Text('暂无可用来源')
            .fontSize(13)
            .fontColor($r('app.color.text_secondary'))
            .layoutWeight(1)
        } else if (this.selectedSourceId === null) {
          Text('点击选择来源')
            .fontSize(14)
            .fontColor($r('app.color.text_secondary'))
            .layoutWeight(1)
        } else {
          Row() {
            ForEach(this.sources, (source: MovieSource) => {
              if (source.id === this.selectedSourceId) {
                Column({ space: 2 }) {
                  Text(source.title)
                    .fontSize(14)
                    .fontColor($r('app.color.text_primary'))
                    .maxLines(1)
                    .textOverflow({ overflow: TextOverflow.Ellipsis })
                  Text(`${SourceDisplay.websiteLabel(source.website)} · ${source.category} · ${SourceDisplay.availabilityLabel(source.availability)}`)
                    .fontSize(12)
                    .fontColor($r('app.color.text_secondary'))
                }
                .layoutWeight(1)
                .alignItems(HorizontalAlign.Start)
              }
            }, (source: MovieSource) => source.id)
          }
          .layoutWeight(1)
        }
        SymbolGlyph($r('sys.symbol.chevron_right'))
          .fontSize(16)
          .fontColor([$r('app.color.text_secondary')])
      }
      .width('100%')
      .height(56)
      .padding({ left: 14, right: 14, top: 10, bottom: 10 })
      .backgroundColor($r('app.color.surface'))
      .borderRadius(8)
      .border({ width: 0.5, color: $r('app.color.divider') })
      .onClick(() => this.openSourceSheet())
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  descriptionBlock() {
    Column({ space: 8 }) {
      Text('简介')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.description !== null && this.description.length > 0) {
        Text(this.description)
          .fontSize(14)
          .fontColor($r('app.color.text_primary'))
          .lineHeight(22)
          .width('100%')
      } else if (this.descriptionOriginal !== null && this.descriptionOriginal.length > 0) {
        Text(`${this.descriptionOriginal}（原文）`)
          .fontSize(14)
          .fontColor($r('app.color.text_primary'))
          .lineHeight(22)
          .width('100%')
      } else {
        Text('暂无简介')
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12 })
  }

  @Builder
  plotBlock() {
    Column({ space: 8 }) {
      Text('剧照')
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor($r('app.color.text_primary'))
        .width('100%')
      if (this.plotUrls.length === 0) {
        Text('暂无剧照')
          .fontSize(13)
          .fontColor($r('app.color.text_secondary'))
          .width('100%')
      } else {
        Flex({ wrap: FlexWrap.Wrap, justifyContent: FlexAlign.Start }) {
          ForEach(this.plotUrls, (url: string) => {
            Stack() {
              CatalogImage({ url: url })
            }
            .width(`calc((100% - ${(this.plotColumns - 1) * 8}px) / ${this.plotColumns})`)
            .aspectRatio(16 / 9)
            .borderRadius(6)
            .clip(true)
            .margin({ right: 8, bottom: 8 })
          }, (url: string) => url)
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 12, bottom: 24 })
  }

  @Builder
  failureView() {
    Column({ space: 10 }) {
      Text(this.store.isNotFound() ? '影片资料不存在' : '影片详情加载失败')
        .fontSize(15)
        .fontColor($r('app.color.text_primary'))
      if (!this.store.isNotFound()) {
        Button('重试')
          .fontSize(14)
          .onClick(() => this.store.retry())
      }
      Button('返回')
        .fontSize(14)
        .backgroundColor($r('app.color.surface_alt'))
        .fontColor($r('app.color.text_primary'))
        .onClick(() => {
          this.pathStack.pop();
        })
    }
    .justifyContent(FlexAlign.Center)
    .width('100%')
    .height('100%')
  }

  build() {
    if (this.store.status === MovieDetailStatus.FAILED) {
      this.failureView()
    } else {
      Scroll() {
        Column({ space: 0 }) {
          this.headerBlock()
          this.metadataStatusBar()
          this.sourceBlock()
          this.descriptionBlock()
          this.plotBlock()
        }
        .width('100%')
      }
      .width('100%')
      .height('100%')
      .scrollBar(BarState.Off)
      .align(Alignment.Top)
    }
  }
}
