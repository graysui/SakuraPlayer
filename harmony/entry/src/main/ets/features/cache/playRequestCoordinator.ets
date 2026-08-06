/** 全局播放请求协调器（MovieDetailPage submit、BlockingWaitPage 显示共享同一实例）。 */
import { PlayRequestStore } from './PlayRequestStore';

export const playRequestStore = new PlayRequestStore();

/** 播放器路由参数：cache_job.id + 首个 selected_media_id（TASK-310 播放器消费）。 */
export interface PlaybackParam {
  cacheJobId: string;
  mediaId: string | null;
}
