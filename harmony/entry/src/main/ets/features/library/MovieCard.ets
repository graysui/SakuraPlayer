/**
 * 可复用影片卡片（AC-064/067/068）。
 * - 封面（2:3 比例）、番号、标题（2 行截断）、标签 chips。
 * - 播放按钮显示影片级进度：未播放/继续播放 N%/已看完；
 *   TASK-111 前 progress 恒 null（AC-068 只读端口返回 null）。
 * - @Reusable 复用 + LazyForEach 按 movie ID 稳定键控。
 */

import { MovieSummary } from '../../core/api/ApiModels';

@Reusable
@Component
export struct MovieCard {
  @State movie: MovieSummary | null = null;

  aboutToReuse(params: Record<string, ESObject>): void {
    this.movie = params.movie as MovieSummary;
  }

  @Builder
  labelChips() {
    if (this.movie !== null) {
      Row({ space: 4 }) {
        ForEach(this.movie.labels, (label: string) => {
          Text(this.labelText(label))
            .fontSize(9)
            .fontColor($r('app.color.text_secondary'))
            .padding({ left: 5, right: 5, top: 2, bottom: 2 })
            .backgroundColor($r('app.color.surface_alt'))
            .borderRadius(4)
        }, (label: string) => label)
      }
      .width('100%')
      .margin({ top: 4 })
    }
  }

  private labelText(label: string): string {
    if (label === 'subtitle') {
      return '字幕';
    }
    if (label === 'cracked') {
      return '破解';
    }
    if (label === '4k') {
      return '4K';
    }
    if (label === 'censored') {
      return '有码';
    }
    return label;
  }

  private progressLabel(): string {
    const progress = this.movie !== null ? this.movie.progress : null;
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
    // 未知时长但有位置
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

  build() {
    Column({ space: 0 }) {
      // 封面区
      Stack() {
        if (this.movie !== null && this.movie.coverUrl !== null) {
          Image(this.movie.coverUrl)
            .width('100%')
            .height(180)
            .objectFit(ImageFit.Cover)
            .backgroundColor($r('app.color.surface_alt'))
        } else {
          Column() {
            SymbolGlyph($r('sys.symbol.doc'))
              .fontSize(36)
              .fontColor([$r('app.color.text_secondary')])
          }
          .justifyContent(FlexAlign.Center)
          .width('100%')
          .height(180)
          .backgroundColor($r('app.color.surface_alt'))
        }
      }
      .width('100%')

      // 信息区
      Column({ space: 0 }) {
        Text(this.movie !== null ? this.movie.number : '')
          .fontSize(13)
          .fontWeight(FontWeight.Medium)
          .fontColor($r('app.color.text_primary'))
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .width('100%')
        Text(this.movie !== null ? this.movie.title : '')
          .fontSize(11)
          .fontColor($r('app.color.text_secondary'))
          .maxLines(2)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
          .width('100%')
          .margin({ top: 2 })
        this.labelChips()
        // 播放按钮（进度）
        Row({ space: 4 }) {
          if (this.movie !== null && this.movie.progress !== null && this.movie.progress.completed) {
            SymbolGlyph($r('sys.symbol.checkmark'))
              .fontSize(12)
              .fontColor(['#FFFFFF'])
          } else {
            SymbolGlyph($r('sys.symbol.video'))
              .fontSize(12)
              .fontColor(['#FFFFFF'])
          }
          Text(this.progressLabel())
            .fontSize(11)
            .fontColor('#FFFFFF')
        }
        .justifyContent(FlexAlign.Center)
        .width('100%')
        .height(30)
        .backgroundColor($r('app.color.primary'))
        .borderRadius(6)
        .margin({ top: 6 })
      }
      .width('100%')
      .padding(8)
      .alignItems(HorizontalAlign.Start)
    }
    .width('100%')
    .backgroundColor($r('app.color.surface'))
    .borderRadius(10)
    .border({ width: 0.5, color: $r('app.color.divider') })
    .clip(true)
  }
}
