/**
 * 115 扫码绑定 Store（AC-013/016）。
 *
 * - 绑定状态：unbound/expired/detached 提供扫码入口；active 显示脱敏账号与缓存根；
 *   unavailable 保留绑定并提供连接重试（不自动清除 Cookie 或要求重新扫码）。
 * - QR 会话状态机：waiting/scanned 每 2 秒轮询一次（single-flight，generation 防过期）；
 *   confirmed 只触发一次 confirm；expired/canceled/not_found 显示重新扫码；
 *   cloud115_unavailable/rate_limited/protocol_error 停止自动轮询并保留非秘密状态。
 * - cloud115_credentials_expired 明确显示"凭据已失效，请重新扫码"，与 unavailable 文案分离。
 * - PNG bytes/会话 ID/过期时间只在内存保存；确认成功、过期、取消、认证变化或离开时清空。
 * - 解绑是独立危险操作（页面二次确认后调用），活动缓存 409 保留绑定。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, Cloud115Binding, QrSession } from '../../core/api/ApiModels';

export enum QrBindingStatus {
  IDLE,
  CREATING,
  POLLING,
  CONFIRMED,
  EXPIRED,
  CANCELED,
  FAILED,
  UNAVAILABLE,
  CREDENTIALS_EXPIRED,
  UNBINDING,
}

@ObservedV2
export class QrBindingStore {
  private readonly pollIntervalMs: number;

  constructor(pollIntervalMs: number = 2000) {
    this.pollIntervalMs = pollIntervalMs;
  }

  @Trace binding: Cloud115Binding | null = null;
  @Trace status: QrBindingStatus = QrBindingStatus.IDLE;
  @Trace sessionId: string | null = null;
  @Trace expiresAt: string | null = null;
  @Trace qrPngBase64: string | null = null;
  @Trace errorCode: string | null = null;
  @Trace errorMessage: string | null = null;
  @Trace unbinding: boolean = false;

  private apiClient: ApiClient | null = null;
  private generation: number = 0;
  private pollTimer: number | null = null;
  private pollInFlight: boolean = false;
  private readonly changeListeners: (() => void)[] = [];

  attach(client: ApiClient | null): void {
    this.apiClient = client;
  }

  addChangeListener(listener: () => void): void {
    if (!this.changeListeners.includes(listener)) {
      this.changeListeners.push(listener);
    }
  }

  removeChangeListener(listener: () => void): void {
    const index = this.changeListeners.indexOf(listener);
    if (index >= 0) {
      this.changeListeners.splice(index, 1);
    }
  }

  /** 认证/会话变化：清空 QR 会话、PNG 与在途状态。 */
  detach(): void {
    this.apiClient = null;
    this.generation++;
    this.stopPolling();
    this.binding = null;
    this.status = QrBindingStatus.IDLE;
    this.sessionId = null;
    this.expiresAt = null;
    this.qrPngBase64 = null;
    this.errorCode = null;
    this.errorMessage = null;
    this.unbinding = false;
  }

  /** 加载绑定状态（设置页进入时）。 */
  loadBinding(): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = ++this.generation;
    client.getCloud115Binding().then((binding: Cloud115Binding) => {
      if (gen !== this.generation) {
        return;
      }
      this.binding = binding;
      this.errorCode = null;
      this.errorMessage = null;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.errorCode = this.errorCodeOf(err);
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** 开始扫码：清空旧会话后创建新 QR。 */
  startQr(): void {
    const client = this.apiClient;
    if (client === null || this.status === QrBindingStatus.CREATING) {
      return;
    }
    this.stopPolling();
    this.clearSession();
    const gen = ++this.generation;
    this.status = QrBindingStatus.CREATING;
    this.notifyChanged();
    client.createCloud115QrSession().then((session: QrSession) => {
      if (gen !== this.generation) {
        return;
      }
      this.sessionId = session.id;
      this.expiresAt = session.expiresAt;
      this.qrPngBase64 = session.qrcodePngBase64;
      this.errorCode = null;
      this.errorMessage = null;
      if (session.status === 'confirmed') {
        this.confirm(session.id);
      } else if (session.status === 'expired') {
        this.clearSession();
        this.status = QrBindingStatus.EXPIRED;
        this.notifyChanged();
      } else if (session.status === 'canceled') {
        this.clearSession();
        this.status = QrBindingStatus.CANCELED;
        this.notifyChanged();
      } else {
        this.status = QrBindingStatus.POLLING;
        this.notifyChanged();
        this.schedulePoll();
      }
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.handleQrError(err);
    });
  }

  /** 取消扫码：清会话并停止轮询。 */
  cancelQr(): void {
    this.stopPolling();
    this.clearSession();
    this.status = QrBindingStatus.CANCELED;
    this.notifyChanged();
  }

  /** 解绑（页面二次确认后调用；活动缓存 409 保留绑定）。 */
  unbind(): void {
    const client = this.apiClient;
    if (client === null || this.unbinding) {
      return;
    }
    const gen = ++this.generation;
    this.unbinding = true;
    this.notifyChanged();
    client.deleteCloud115Binding().then(() => {
      if (gen !== this.generation) {
        return;
      }
      this.unbinding = false;
      this.stopPolling();
      this.clearSession();
      this.status = QrBindingStatus.IDLE;
      this.binding = null;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.unbinding = false;
      this.errorCode = this.errorCodeOf(err);
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** 确认成功/错误后由页面调用以刷新绑定。 */
  reloadBinding(): void {
    this.loadBinding();
  }

  private schedulePoll(): void {
    if (this.pollTimer !== null) {
      return;
    }
    this.pollTimer = setTimeout(() => {
      this.pollTimer = null;
      this.pollOnce();
    }, this.pollIntervalMs);
  }

  private pollOnce(): void {
    if (this.pollInFlight) {
      this.schedulePoll();
      return;
    }
    const sessionId = this.sessionId;
    const client = this.apiClient;
    if (sessionId === null || client === null) {
      return;
    }
    this.pollInFlight = true;
    const gen = this.generation;
    client.getCloud115QrSession(sessionId).then((session: QrSession) => {
      this.pollInFlight = false;
      if (gen !== this.generation) {
        return;
      }
      if (session.status === 'confirmed') {
        this.confirm(session.id);
      } else if (session.status === 'expired') {
        this.stopPolling();
        this.clearSession();
        this.status = QrBindingStatus.EXPIRED;
        this.notifyChanged();
      } else if (session.status === 'canceled') {
        this.stopPolling();
        this.clearSession();
        this.status = QrBindingStatus.CANCELED;
        this.notifyChanged();
      } else {
        // waiting/scanned：继续轮询
        this.schedulePoll();
      }
    }).catch((err: Error) => {
      this.pollInFlight = false;
      if (gen !== this.generation) {
        return;
      }
      this.handleQrError(err);
    });
  }

  private confirm(sessionId: string): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    this.stopPolling();
    this.status = QrBindingStatus.POLLING;
    this.notifyChanged();
    const gen = this.generation;
    client.confirmCloud115QrSession(sessionId).then((binding: Cloud115Binding) => {
      if (gen !== this.generation) {
        return;
      }
      this.clearSession();
      this.binding = binding;
      this.status = QrBindingStatus.CONFIRMED;
      this.errorCode = null;
      this.errorMessage = null;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.handleQrError(err);
    });
  }

  private handleQrError(err: Error): void {
    const code = this.errorCodeOf(err);
    if (code === 'cloud115_credentials_expired') {
      this.stopPolling();
      this.clearSession();
      this.status = QrBindingStatus.CREDENTIALS_EXPIRED;
    } else if (code === 'cloud115_qr_session_not_found') {
      this.stopPolling();
      this.clearSession();
      this.status = QrBindingStatus.EXPIRED;
    } else if (code === 'cloud115_unavailable' || code === 'rate_limited' ||
      code === 'protocol_error') {
      // 停止自动轮询并保留绑定状态；PNG/会话属秘密须清空，用户显式重试
      this.stopPolling();
      this.clearSession();
      this.status = QrBindingStatus.UNAVAILABLE;
    } else {
      this.stopPolling();
      this.clearSession();
      this.status = QrBindingStatus.FAILED;
    }
    this.errorCode = code;
    this.errorMessage = this.errorTextOf(err);
    this.notifyChanged();
  }

  private clearSession(): void {
    this.sessionId = null;
    this.expiresAt = null;
    this.qrPngBase64 = null;
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private errorCodeOf(err: Error): string {
    if (err instanceof ApiException) {
      return err.code;
    }
    return 'client_transport_error';
  }

  private errorTextOf(err: Error): string {
    const code = this.errorCodeOf(err);
    if (code === 'cloud115_credentials_expired') {
      return '凭据已失效，请重新扫码';
    }
    if (code === 'cloud115_unavailable') {
      return '115 暂时不可用，请稍后重试';
    }
    if (code === 'rate_limited') {
      return '115 请求过于频繁，请稍后重试';
    }
    if (code === 'cloud115_qr_session_not_found') {
      return '二维码已失效，请重新扫码';
    }
    if (code === 'cache_active_lease') {
      return '存在正在播放的缓存任务，暂时不能解绑';
    }
    if (code === 'client_transport_error') {
      return '无法连接服务器，请稍后重试';
    }
    return '操作失败，请重试';
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}

/** 全局 QR 绑定 store 单例（设置页使用）。 */
export const qrBindingStore = new QrBindingStore();
