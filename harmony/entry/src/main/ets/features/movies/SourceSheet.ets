/**
 * 多来源选择 bottom sheet（AC-031/033/034/035）。
 *
 * - 保持服务端来源顺序的可扫描列表；每行：站点、分类、日期、标题（最多 2 行省略）、
 *   状态、大小、叠加标签（固定顺序 字幕/破解/4K/有码）。
 * - rejected 永久禁用且不得输出 source_id；选择行本身不访问网络。
 * - 由 MovieDetailPage 通过 UIContext.openBindSheet 打开（非 deprecated API）。
 */

import { MovieSource } from '../../core/api/ApiModels';

/** 来源展示文案工具（页面与测试共用）。 */
export class SourceDisplay {
  static websiteLabel(website: string): string {
    if (website === 'sehuatang') {
      return '色花堂';
    }
    if (website === 'x1080x') {
      return 'X1080X';
    }
    return website;
  }

  static availabilityLabel(availability: string): string {
    if (availability === 'available') {
      return '可缓存';
    }
    if (availability === 'queued') {
      return '排队中';
    }
    if (availability === 'running') {
      return '处理中';
    }
    if (availability === 'ready') {
      return '可播放';
    }
    if (availability === 'failed') {
      return '上次失败';
    }
    if (availability === 'rejected') {
      return '不可用';
    }
    return availability;
  }

  static labelText(label: string): string {
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

  /** 标签固定显示顺序（服务端标签只显示，不推导）。 */
  static orderedLabels(labels: string[]): string[] {
    const order: string[] = ['subtitle', 'cracked', '4k', 'censored'];
    const result: string[] = [];
    for (const key of order) {
      if (labels.includes(key)) {
        result.push(SourceDisplay.labelText(key));
      }
    }
    return result;
  }

  /** 大小文案：ready 显示视频文件大小，其余显示资源大小；空值显示"未知"。 */
  static sizeLabel(source: MovieSource): string {
    if (source.availability === 'ready') {
      if (source.videoFileSizeBytes === null) {
        return '视频文件大小未知';
      }
      return `视频文件大小 ${SourceDisplay.formatBytes(source.videoFileSizeBytes)}`;
    }
    if (source.resourceSizeMb === null) {
      return '资源大小未知';
    }
    return `资源大小 ${Math.round(source.resourceSizeMb)} MiB`;
  }

  static formatBytes(bytes: number): string {
    const gib = bytes / (1024 * 1024 * 1024);
    if (gib >= 1) {
      return `${SourceDisplay.compact(gib)} GiB`;
    }
    const mib = bytes / (1024 * 1024);
    if (mib >= 1) {
      return `${SourceDisplay.compact(mib)} MiB`;
    }
    return `${Math.round(bytes)} B`;
  }

  private static compact(value: number): string {
    const rounded = Math.round(value * 10) / 10;
    if (Math.floor(rounded) === rounded) {
      return `${Math.floor(rounded)}`;
    }
    return `${rounded}`;
  }
}

/** SourceSheet 构造参数。 */
export interface SourceSheetParams {
  sources: MovieSource[];
  selectedSourceId: string | null;
  onSelect: (sourceId: string) => void;
}

/** 来源 bottom sheet 内容（由页面 openBindSheet 挂载）。 */
@Builder
export function SourceSheetBuilder(params: SourceSheetParams) {
  Column({ space: 0 }) {
    if (params.sources.length === 0) {
      Text('暂无可用来源')
        .fontSize(14)
        .fontColor($r('app.color.text_secondary'))
        .margin({ top: 24, bottom: 24 })
    } else {
      List({ space: 0 }) {
        ForEach(params.sources, (source: MovieSource) => {
          ListItem() {
            Row({ space: 10 }) {
              Radio({ value: source.id, group: 'source' })
                .checked(params.selectedSourceId === source.id)
                .enabled(source.isSelectable())
              Column({ space: 4 }) {
                Text(source.title)
                  .fontSize(14)
                  .fontWeight(FontWeight.Medium)
                  .fontColor($r('app.color.text_primary'))
                  .maxLines(2)
                  .textOverflow({ overflow: TextOverflow.Ellipsis })
                  .width('100%')
                Row({ space: 6 }) {
                  Text(SourceDisplay.websiteLabel(source.website))
                    .fontSize(11)
                    .fontColor($r('app.color.text_secondary'))
                    .maxLines(1)
                  Text(source.category)
                    .fontSize(11)
                    .fontColor($r('app.color.text_secondary'))
                    .maxLines(1)
                  if (source.publishDate !== null) {
                    Text(source.publishDate)
                      .fontSize(11)
                      .fontColor($r('app.color.text_secondary'))
                      .maxLines(1)
                  }
                  ForEach(SourceDisplay.orderedLabels(source.labels), (label: string) => {
                    Text(label)
                      .fontSize(10)
                      .fontColor($r('app.color.primary'))
                      .padding({ left: 5, right: 5, top: 1, bottom: 1 })
                      .borderRadius(4)
                      .border({ width: 0.5, color: $r('app.color.primary') })
                  }, (label: string) => label)
                }
                .width('100%')
              }
              .layoutWeight(1)
              .alignItems(HorizontalAlign.Start)
              Column({ space: 2 }) {
                Text(SourceDisplay.availabilityLabel(source.availability))
                  .fontSize(12)
                  .fontColor(source.isSelectable() ? $r('app.color.primary') : $r('app.color.text_secondary'))
                Text(SourceDisplay.sizeLabel(source))
                  .fontSize(11)
                  .fontColor($r('app.color.text_secondary'))
                  .maxLines(1)
                  .textOverflow({ overflow: TextOverflow.Ellipsis })
              }
              .alignItems(HorizontalAlign.End)
            }
            .width('100%')
            .height(88)
            .padding({ left: 16, right: 16, top: 12, bottom: 12 })
            .backgroundColor(params.selectedSourceId === source.id ? $r('app.color.surface_alt') : Color.Transparent)
            .onClick(() => {
              if (source.isSelectable()) {
                params.onSelect(source.id);
              }
            })
          }
          .width('100%')
        }, (source: MovieSource) => source.id)
      }
      .width('100%')
      .height('100%')
    }
  }
  .width('100%')
  .padding({ top: 8, bottom: 16 })
}
