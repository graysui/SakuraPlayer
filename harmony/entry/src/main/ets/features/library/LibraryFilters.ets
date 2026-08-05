/**
 * 组合筛选 sheet（AC-063/064/077）：
 * 六分类多选（OR）、四标签叠加（AND）、来源、可播放、资源大小范围、
 * 收藏、排序；应用即触发刷新，重置清空。
 */

import { LengthMetrics } from '@kit.ArkUI';
import { libraryStore, LibraryFilters } from './LibraryStore';

@Component
export struct LibraryFiltersSheet {
  @State minSizeText: string = '';
  @State maxSizeText: string = '';
  onDismiss: () => void = () => {};

  private onApply(): void {
    const min = this.sizeValue(this.minSizeText);
    const max = this.sizeValue(this.maxSizeText);
    libraryStore.setSizeRange(min, max);
    this.onDismiss();
  }

  private sizeValue(text: string): number | null {
    const trimmed = text.trim();
    if (trimmed.length === 0) {
      return null;
    }
    const parsed = Number.parseInt(trimmed, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }

  @Builder
  sectionTitle(title: string) {
    Text(title)
      .fontSize(14)
      .fontWeight(FontWeight.Medium)
      .fontColor($r('app.color.text_primary'))
      .width('100%')
      .margin({ top: 12, bottom: 6 })
  }

  @Builder
  chipRow(options: string[], selected: string[], onToggle: (value: string) => void) {
    Flex({ wrap: FlexWrap.Wrap, space: { main: LengthMetrics.vp(8), cross: LengthMetrics.vp(8) } }) {
      ForEach(options, (option: string) => {
        Text(option)
          .fontSize(12)
          .fontColor(selected.includes(option) ? '#FFFFFF' : $r('app.color.text_primary'))
          .padding({ left: 12, right: 12, top: 6, bottom: 6 })
          .backgroundColor(selected.includes(option) ? $r('app.color.primary') : $r('app.color.surface_alt'))
          .borderRadius(14)
          .onClick(() => onToggle(option))
      }, (option: string) => option)
    }
    .width('100%')
  }

  @Builder
  sourceRow() {
    Row({ space: 8 }) {
      ForEach(['全部', 'sehuatang', 'x1080x'], (option: string) => {
        Text(option)
          .fontSize(12)
          .fontColor(this.sourceSelected(option) ? '#FFFFFF' : $r('app.color.text_primary'))
          .padding({ left: 12, right: 12, top: 6, bottom: 6 })
          .backgroundColor(this.sourceSelected(option) ? $r('app.color.primary') : $r('app.color.surface_alt'))
          .borderRadius(14)
          .onClick(() => {
            libraryStore.setSource(option === '全部' ? null : option);
          })
      }, (option: string) => option)
    }
    .width('100%')
  }

  private sourceSelected(option: string): boolean {
    if (option === '全部') {
      return libraryStore.sourceWebsite === null;
    }
    return libraryStore.sourceWebsite === option;
  }

  @Builder
  playableRow() {
    Row({ space: 8 }) {
      ForEach(['全部', '仅可播放', '不可播放'], (option: string) => {
        Text(option)
          .fontSize(12)
          .fontColor(this.playableSelected(option) ? '#FFFFFF' : $r('app.color.text_primary'))
          .padding({ left: 12, right: 12, top: 6, bottom: 6 })
          .backgroundColor(this.playableSelected(option) ? $r('app.color.primary') : $r('app.color.surface_alt'))
          .borderRadius(14)
          .onClick(() => {
            if (option === '全部') {
              libraryStore.setPlayable(null);
            } else if (option === '仅可播放') {
              libraryStore.setPlayable(true);
            } else {
              libraryStore.setPlayable(false);
            }
          })
      }, (option: string) => option)
    }
    .width('100%')
  }

  private playableSelected(option: string): boolean {
    if (option === '全部') {
      return libraryStore.playable === null;
    }
    if (option === '仅可播放') {
      return libraryStore.playable === true;
    }
    return libraryStore.playable === false;
  }

  @Builder
  sortRow() {
    Row({ space: 8 }) {
      ForEach([['publish_date_desc', '最新发行'], ['publish_date_asc', '最早发行'], ['number_asc', '番号排序']],
        (option: string[]) => {
          Text(option[1])
            .fontSize(12)
            .fontColor(libraryStore.sort === option[0] ? '#FFFFFF' : $r('app.color.text_primary'))
            .padding({ left: 12, right: 12, top: 6, bottom: 6 })
            .backgroundColor(libraryStore.sort === option[0] ? $r('app.color.primary') : $r('app.color.surface_alt'))
            .borderRadius(14)
            .onClick(() => libraryStore.setSort(option[0]))
        }, (option: string[]) => option[0])
    }
    .width('100%')
  }

  build() {
    Column() {
      Scroll() {
        Column({ space: 0 }) {
          this.sectionTitle('分类（可多选）')
          this.chipRow(LibraryFilters.CATEGORIES, libraryStore.categories,
            (value: string) => libraryStore.toggleCategory(value))
          this.sectionTitle('标签（可叠加）')
          this.chipRow(LibraryFilters.LABELS, libraryStore.labels,
            (value: string) => libraryStore.toggleLabel(value))
          this.sectionTitle('来源')
          this.sourceRow()
          this.sectionTitle('可播放')
          this.playableRow()
          this.sectionTitle('资源大小（MB）')
          Row({ space: 8 }) {
            TextInput({ placeholder: '最小', text: this.minSizeText })
              .type(InputType.Number)
              .layoutWeight(1)
              .onChange((value: string) => {
                this.minSizeText = value;
              })
            TextInput({ placeholder: '最大', text: this.maxSizeText })
              .type(InputType.Number)
              .layoutWeight(1)
              .onChange((value: string) => {
                this.maxSizeText = value;
              })
          }
          .width('100%')
          this.sectionTitle('排序')
          this.sortRow()
          Row({ space: 10 }) {
            Toggle({ type: ToggleType.Switch, isOn: libraryStore.favorite })
              .selectedColor($r('app.color.primary'))
              .onChange((isOn: boolean) => {
                libraryStore.setFavorite(isOn);
              })
            Text('仅看收藏')
              .fontSize(13)
              .fontColor($r('app.color.text_primary'))
            Blank()
          }
          .width('100%')
          .margin({ top: 12 })
        }
        .width('100%')
        .padding(16)
      }
      .width('100%')
      .layoutWeight(1)

      Row({ space: 10 }) {
        Button('重置')
          .layoutWeight(1)
          .backgroundColor($r('app.color.surface_alt'))
          .fontColor($r('app.color.text_primary'))
          .onClick(() => {
            this.minSizeText = '';
            this.maxSizeText = '';
            libraryStore.resetFilters();
            this.onDismiss();
          })
        Button('应用')
          .layoutWeight(1)
          .onClick(() => this.onApply())
      }
      .width('100%')
      .padding(16)
      .backgroundColor($r('app.color.surface'))
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.surface'))
  }
}
