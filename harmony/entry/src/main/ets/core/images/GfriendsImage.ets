/**
 * GFriends 图片组件（AC-051/052/053）：按 URL 经 GfriendsCache 加载 PixelMap。
 * - URL 变化（@Reusable aboutToReuse）重新加载；离屏 generation 失效丢弃迟到结果。
 * - 加载中/失败显示固定占位，不抛错、不影响同页其他图片。
 * - 图片生命周期由 GfriendsCache（cacheDir/gfriends-v1 + 内存 LRU）管理。
 */

import { image } from '@kit.ImageKit';
import { gfriendsCache } from './GfriendsCache';

@Reusable
@Component
export struct GfriendsImage {
  @State url: string | null = null;
  @State pixelMap: image.PixelMap | null = null;
  private generation: number = 0;

  aboutToAppear(): void {
    // 首次创建（非复用路径）也需要加载
    this.reload();
  }

  aboutToReuse(params: Record<string, ESObject>): void {
    const next = params.url as string | null;
    if (next !== this.url) {
      this.url = next;
      this.reload();
    }
  }

  aboutToDisappear(): void {
    // 离屏：丢弃在途结果并释放引用（缓存 LRU 继续持有最近图片）
    this.generation++;
    this.pixelMap = null;
  }

  private reload(): void {
    const url = this.url;
    if (url === null) {
      this.pixelMap = null;
      return;
    }
    const gen = ++this.generation;
    this.pixelMap = null;
    const cache = gfriendsCache.cacheInstance;
    if (cache === null) {
      return;
    }
    cache.load(url).then((pixelMap: image.PixelMap | null) => {
      if (gen === this.generation && pixelMap !== null) {
        this.pixelMap = pixelMap;
      }
    }).catch(() => {
      // 单图失败：保持占位
    });
  }

  build() {
    if (this.pixelMap !== null) {
      Image(this.pixelMap)
        .width('100%')
        .height('100%')
        .objectFit(ImageFit.Cover)
        .backgroundColor($r('app.color.surface_alt'))
    } else {
      Column() {
        SymbolGlyph($r('sys.symbol.person'))
          .fontSize(36)
          .fontColor([$r('app.color.text_secondary')])
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .height('100%')
      .backgroundColor($r('app.color.surface_alt'))
    }
  }
}
