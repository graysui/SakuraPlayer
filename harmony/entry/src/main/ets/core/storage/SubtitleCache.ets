/**
 * 私有字幕缓存（AC-108/109/110、TASK-110 契约）。
 *
 * - 目录：cacheDir/subtitles；文件名只使用 subtitle UUID + 白名单扩展名（防路径穿越）。
 * - 映射：index.json 存 cache_job_id -> [subtitle_id]（cache.job.cleaned.v1 按 job 删除）。
 * - 生命周期：logout clear 清空全部；本地过期（subtitle_cache_expires_at）清空全部；
 *   三类清理都不影响永久图片缓存。
 * - 同名优先：{id}.{ext} 已存在则复用；下载/加载失败返回 null 不阻止视频。
 */

import { fileIo as fs } from '@kit.CoreFileKit';
import { common } from '@kit.AbilityKit';
import { ApiClient } from '../api/ApiClient';
import { SubtitleOption } from '../api/ApiModels';

export class SubtitleCache {
  static readonly DIR_NAME = 'subtitles';
  static readonly EXTENSIONS: string[] = ['srt', 'ass', 'ssa', 'vtt'];
  private static readonly INDEX_NAME = 'index.json';

  /** 返回字幕缓存目录绝对路径。 */
  static dir(context: common.Context): string {
    return `${context.cacheDir}/${SubtitleCache.DIR_NAME}`;
  }

  /** 递归清理整个字幕缓存目录（logout，AC-012/AC-110）。 */
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

  /** 本地副本服务端上限到期（subtitle_cache_expires_at）：清空全部字幕。 */
  static async removeExpired(context: common.Context): Promise<void> {
    await SubtitleCache.clear(context);
  }

  /** 校验 subtitle id + format（路径穿越防护：只允许 UUID + 白名单扩展名）。 */
  static isSafeId(subtitleId: string, format: string): boolean {
    if (!/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(subtitleId)) {
      return false;
    }
    return SubtitleCache.EXTENSIONS.includes(format);
  }

  /** 本地文件路径（{dir}/{id}.{ext}）；非法 id/format 抛错。 */
  static pathFor(context: common.Context, subtitleId: string, format: string): string {
    if (!SubtitleCache.isSafeId(subtitleId, format)) {
      throw new Error('subtitle cache path must be uuid + whitelisted extension');
    }
    return `${SubtitleCache.dir(context)}/${subtitleId}.${format}`;
  }

  /** 同名优先：本地已有 {id}.{ext}（任一白名单扩展名）返回 true。 */
  static exists(context: common.Context, subtitleId: string): boolean {
    if (!/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(subtitleId)) {
      return false;
    }
    for (const ext of SubtitleCache.EXTENSIONS) {
      const path = `${SubtitleCache.dir(context)}/${subtitleId}.${ext}`;
      try {
        if (fs.accessSync(path) && fs.statSync(path).isFile()) {
          return true;
        }
      } catch (err) {
        // 文件不存在
      }
    }
    return false;
  }

  /** 下载字幕到私有缓存；已有副本复用；失败返回 null（不阻止视频）。 */
  static async download(context: common.Context, client: ApiClient | null,
    subtitle: SubtitleOption, cacheJobId: string): Promise<string | null> {
    if (!SubtitleCache.isSafeId(subtitle.id, subtitle.format)) {
      return null;
    }
    const dir = SubtitleCache.dir(context);
    try {
      if (!fs.accessSync(dir)) {
        fs.mkdirSync(dir, true);
      }
    } catch (err) {
      return null;
    }
    const path = SubtitleCache.pathFor(context, subtitle.id, subtitle.format);
    if (SubtitleCache.exists(context, subtitle.id)) {
      return path; // 同名优先
    }
    if (client === null) {
      return null;
    }
    try {
      const text = await client.downloadSubtitle(subtitle.id);
      SubtitleCache.writeTextFile(path, text);
      await SubtitleCache.recordJobMapping(context, cacheJobId, subtitle.id);
      return path;
    } catch (err) {
      return null; // 字幕失败不阻止视频
    }
  }

  /** cache.job.cleaned.v1：按 job 删除对应副本（AC-110）。 */
  static async removeForJob(context: common.Context, cacheJobId: string): Promise<void> {
    const dir = SubtitleCache.dir(context);
    let index: Record<string, Object>;
    try {
      if (!fs.accessSync(`${dir}/${SubtitleCache.INDEX_NAME}`)) {
        return;
      }
      index = JSON.parse(fs.readTextSync(`${dir}/${SubtitleCache.INDEX_NAME}`)) as Record<string, Object>;
    } catch (err) {
      return;
    }
    const jobs = index['jobs'];
    if (typeof jobs !== 'object' || jobs === null) {
      return;
    }
    const emptyJobs: Record<string, Object> = new Object() as Record<string, Object>;
    const jobMap = (typeof jobs === 'object' && jobs !== null) ?
      jobs as Record<string, Object> : emptyJobs;
    const idsRaw = jobMap[cacheJobId];
    if (Array.isArray(idsRaw)) {
      const ids = idsRaw as string[];
      for (const raw of ids) {
        if (typeof raw !== 'string') {
          continue;
        }
        SubtitleCache.removeFilesForId(context, raw);
      }
    }
    // ArkTS 无 delete：重建 jobs 映射（排除该 jobId）
    const remaining: Record<string, Object> = new Object() as Record<string, Object>;
    for (const key of Object.keys(jobMap)) {
      if (key !== cacheJobId) {
        remaining[key] = jobMap[key];
      }
    }
    index['jobs'] = remaining;
    try {
      SubtitleCache.writeTextFile(`${dir}/${SubtitleCache.INDEX_NAME}`, JSON.stringify(index));
    } catch (err) {
      // 映射写失败：文件已删，下次重建
    }
  }

  private static async recordJobMapping(context: common.Context, cacheJobId: string,
    subtitleId: string): Promise<void> {
    const dir = SubtitleCache.dir(context);
    const indexPath = `${dir}/${SubtitleCache.INDEX_NAME}`;
    let index: Record<string, Object>;
    try {
      index = fs.accessSync(indexPath) ?
        JSON.parse(fs.readTextSync(indexPath)) as Record<string, Object> : {};
    } catch (err) {
      index = new Object() as Record<string, Object>;
    }
    if (index['jobs'] === undefined || typeof index['jobs'] !== 'object') {
      index['jobs'] = new Object() as Record<string, Object>;
    }
    const jobMap = index['jobs'] as Record<string, Object>;
    const listRaw = jobMap[cacheJobId];
    const list: string[] = Array.isArray(listRaw) ? listRaw as string[] : [];
    if (!list.includes(subtitleId)) {
      list.push(subtitleId);
    }
    jobMap[cacheJobId] = list;
    try {
      SubtitleCache.writeTextFile(indexPath, JSON.stringify(index));
    } catch (err) {
      // 映射写失败：字幕文件仍在，仅失去按 job 清理索引
    }
  }

  /** 文本写文件（fileIo 无 writeTextSync：open + writeSync + close）。 */
  private static writeTextFile(path: string, text: string): void {
    const fd = fs.openSync(path, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    try {
      fs.writeSync(fd.fd, text);
    } finally {
      fs.closeSync(fd.fd);
    }
  }

  private static removeFilesForId(context: common.Context, subtitleId: string): void {
    if (!/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(subtitleId)) {
      return;
    }
    for (const ext of SubtitleCache.EXTENSIONS) {
      try {
        const path = `${SubtitleCache.dir(context)}/${subtitleId}.${ext}`;
        if (fs.accessSync(path) && fs.statSync(path).isFile()) {
          fs.unlinkSync(path);
        }
      } catch (err) {
        // 文件不存在
      }
    }
  }

  private static async removeRecursive(path: string): Promise<void> {
    try {
      const entries = fs.listFileSync(path);
      for (const name of entries) {
        const child = `${path}/${name}`;
        // lstat：不跟随符号链接（防御目录内被植入指向外部目录的 symlink）
        const stat = fs.lstatSync(child);
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
