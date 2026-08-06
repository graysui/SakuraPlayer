/**
 * 本地完成通知（TASK-308；进程存活期间投递，不申请常驻后台权限）。
 *
 * - 数据源：SnapshotStore 的通知（notification.created 事件/恢复快照未读）。
 * - 只对 cache_started/cache_ready/cache_failed/credential_expired 四类发布本地通知；
 *   已读或已发布（同 id）跳过。
 * - 显示成功后调用 PUT /notifications/{id}/read 标记已读。
 * - 完全退出后无后台代理：下次启动快照补拉未读通知。
 */

import { notificationManager } from '@kit.NotificationKit';
import { Notification } from '../api/ApiModels';
import { SnapshotListener, SnapshotStore } from '../events/SnapshotStore';
import { ApiClient } from '../api/ApiClient';

/** 通知内容映射（不包含任何秘密/磁力/URL）。 */
function contentFor(type: string): [string, string] | null {
  if (type === 'cache_started') {
    return ['缓存任务开始', '任务正在后台处理，不会自动播放'];
  }
  if (type === 'cache_ready') {
    return ['缓存已就绪', '可在缓存页查看并播放'];
  }
  if (type === 'cache_failed') {
    return ['缓存任务失败', '可在缓存页查看失败原因'];
  }
  if (type === 'credential_expired') {
    return ['115 凭据已失效', '请在设置中重新扫码'];
  }
  return null;
}

export class AppNotifications {
  private snapshot: SnapshotStore | null = null;
  private listener: SnapshotListener = (): void => {
    this.deliverPending();
  };
  private publishedIds: string[] = [];
  private nextId: number = 1;

  attach(snapshot: SnapshotStore | null): void {
    this.detach();
    this.snapshot = snapshot;
    if (snapshot !== null) {
      snapshot.addListener(this.listener);
    }
  }

  detach(): void {
    if (this.snapshot !== null) {
      this.snapshot.removeListener(this.listener);
      this.snapshot = null;
    }
  }

  /** 认证变化/退出登录：清空已发布记录（新会话重新投递未读）。 */
  reset(): void {
    this.publishedIds = [];
  }

  private deliverPending(): void {
    const snapshot = this.snapshot;
    if (snapshot === null) {
      return;
    }
    const notifications = snapshot.notificationList;
    for (const notification of notifications) {
      if (notification.readAt !== null) {
        continue;
      }
      if (this.publishedIds.includes(notification.id)) {
        continue;
      }
      const content = contentFor(notification.type);
      if (content === null) {
        continue;
      }
      this.publish(notification, content[0], content[1]);
    }
  }

  private publish(notification: Notification, title: string, text: string): void {
    const normal: notificationManager.NotificationBasicContent = { title: title, text: text };
    const content: notificationManager.NotificationContent = {
      notificationContentType: notificationManager.ContentType.NOTIFICATION_CONTENT_BASIC_TEXT,
      normal: normal,
    };
    const request: notificationManager.NotificationRequest = {
      id: this.nextId,
      content: content,
      deliveryTime: Date.now(),
    };
    this.nextId++;
    notificationManager.publish(request).then(() => {
      this.publishedIds.push(notification.id);
      // 显示成功后标记已读（失败不重试，下次快照变化再评估）
      const client = this.apiClientOf();
      if (client !== null) {
        client.markNotificationRead(notification.id).catch(() => {
          // 已读标记失败：忽略（不阻断通知流程）
        });
      }
    }).catch(() => {
      // 通知发布失败（无权限等）：不阻断
    });
  }

  private apiClientOf(): ApiClient | null {
    // 由外部注入（AuthStore 的当前 client）；无则跳过已读标记
    return this.client;
  }

  private client: ApiClient | null = null;

  setClient(client: ApiClient | null): void {
    this.client = client;
  }
}

/** 全局通知投递单例。 */
export const appNotifications = new AppNotifications();
