/**
 * 认证目录图片组件（AC-074 封面/剧照）。
 * - URL 白名单与内存 LRU 见 core/images/CatalogImageCache（AuthStore.logout 负责清理）。
 * - 单图失败/URL 非法只显示占位；离屏 generation 丢弃迟到结果；复用（含同 URL）重载。
 */

import { image } from '@kit.ImageKit';
import { authStore } from '../../core/auth/AuthStore';
import { catalogImageCache } from '../../core/images/CatalogImageCache';

@Reusable
@Component
export struct CatalogImage {
  @State url: string | null = null;
  @State pixelMap: image.PixelMap | null = null;
  private generation: number = 0;

  aboutToAppear(): void {
    this.reload();
  }

  aboutToReuse(params: Record<string, ESObject>): void {
    const next = params.url as string | null;
    if (next !== this.url) {
      this.url = next;
    }
    // 复用（含同 URL 复用）都重载：aboutToDisappear 已清空 pixelMap
    this.reload();
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
    catalogImageCache.load(url, authStore.apiClientProvider).then((loaded: image.PixelMap | null) => {
      if (gen === this.generation && loaded !== null) {
        this.pixelMap = loaded;
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
    } else {
      Column() {
        SymbolGlyph($r('sys.symbol.doc'))
          .fontSize(28)
          .fontColor([$r('app.color.text_secondary')])
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')
      .height('100%')
      .backgroundColor($r('app.color.surface_alt'))
    }
  }
}
