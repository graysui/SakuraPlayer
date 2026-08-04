/**
 * 私有字幕缓存目录约定与清理（AC-012：logout 删除字幕缓存）。
 * 实际缓存读写由 TASK-311 实现；此处固定目录常量与证明式清理。
 * API 24 fileIo 无递归删除，手动遍历目录树。
 */

import { fileIo as fs } from '@kit.CoreFileKit';
import { common } from '@kit.AbilityKit';

export class SubtitleCache {
  static readonly DIR_NAME = 'subtitles';

  /** 返回字幕缓存目录绝对路径。 */
  static dir(context: common.Context): string {
    return `${context.cacheDir}/${SubtitleCache.DIR_NAME}`;
  }

  /** 递归清理整个字幕缓存目录（TASK-311 写入后目录非空）。 */
  static async clear(context: common.Context): Promise<void> {
    try {
      if (!fs.accessSync(SubtitleCache.dir(context))) {
        return;
      }
      await SubtitleCache.removeRecursive(SubtitleCache.dir(context));
    } catch (err) {
      // 目录不存在或删除失败：不阻塞 logout
    }
  }

  private static async removeRecursive(path: string): Promise<void> {
    try {
      const entries = fs.listFileSync(path);
      for (const name of entries) {
        const child = `${path}/${name}`;
        const stat = fs.statSync(child);
        if (stat.isDirectory()) {
          await SubtitleCache.removeRecursive(child);
        } else {
          fs.unlinkSync(child);
        }
      }
      fs.rmdirSync(path);
    } catch (err) {
      // 单项删除失败：继续其余清理
    }
  }
}
