/**
 * 私有字幕缓存目录约定与清理（AC-012：logout 删除字幕缓存）。
 * 实际缓存读写由 TASK-311 实现；此处固定目录常量与证明式清理。
 */

import { fileIo as fs } from '@kit.CoreFileKit';
import { common } from '@kit.AbilityKit';

export class SubtitleCache {
  static readonly DIR_NAME = 'subtitles';

  /** 返回字幕缓存目录绝对路径。 */
  static dir(context: common.Context): string {
    return `${context.cacheDir}/${SubtitleCache.DIR_NAME}`;
  }

  /** 递归清理整个字幕缓存目录（TASK-311 写入后目录非空，必须递归删除）。 */
  static async clear(context: common.Context): Promise<void> {
    const dir = SubtitleCache.dir(context);
    try {
      const exists = fs.accessSync(dir);
      if (!exists) {
        return;
      }
      fs.rmdirSync(dir, true);
    } catch (err) {
      // 目录不存在或删除失败：不阻塞 logout
    }
  }
}
