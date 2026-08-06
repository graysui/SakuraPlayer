/**
 * 认证会话状态机（AC-002/AC-011/AC-012/AC-133/AC-135）。
 *
 * 状态流转：
 *   initializing → serverRequired（无已存基址）
 *                → unauthenticated（已存基址；无会话或恢复失败）
 *                → authenticated（refresh 静默恢复或登录/bootstrap 成功）
 *
 * bootstrap token 只在单次请求 header 中携带，不落 Preferences/Asset Store/日志。
 * 更换地址或 logout：尽力注销旧会话 + 清本机令牌、字幕缓存与事件状态。
 */

import { preferences } from '@kit.ArkData';
import { util } from '@kit.ArkTS';
import { common } from '@kit.AbilityKit';
import { ApiClient, HttpTransport, NetworkHttpTransport, SessionProvider } from '../api/ApiClient';
import { ServerAddressCodes, ServerAddressException, ServerProfile, ServerProfileStore } from '../api/ServerProfile';
import { ApiException, TokenPair } from '../api/ApiModels';
import { SecureSessionStore } from './SecureSessionStore';
import { EventClient, NetworkWebSocketTransport, WebSocketTransport } from '../events/EventClient';
import { SnapshotStore } from '../events/SnapshotStore';
import { SubtitleCache } from '../storage/SubtitleCache';
import { gfriendsCache } from '../images/GfriendsCache';
import { catalogImageCache } from '../images/CatalogImageCache';

export enum AuthStatus {
  INITIALIZING,
  SERVER_REQUIRED,
  UNAUTHENTICATED,
  AUTHENTICATED,
}

@ObservedV2
export class AuthStore {
  @Trace status: AuthStatus = AuthStatus.INITIALIZING;
  @Trace serverBaseUrl: string = '';
  @Trace bootstrapRequired: boolean = false;
  @Trace busy: boolean = false;
  @Trace errorCode: string | null = null;
  @Trace errorMessage: string | null = null;
  /** 等待用户确认的私网明文 http 地址（原样输入）。 */
  @Trace pendingPrivateHttp: string | null = null;

  private readonly session: SecureSessionStore;
  private apiClient: ApiClient | null = null;
  private eventClient: EventClient | null = null;
  private snapshot: SnapshotStore | null = null;
  private context: common.Context | null = null;
  private clientInstanceIdValue: string = '';
  private testTransport: HttpTransport | null = null;

  constructor() {
    this.session = new SecureSessionStore();
  }

  get sessionProvider(): SessionProvider {
    return this.session;
  }

  get snapshotStore(): SnapshotStore | null {
    return this.snapshot;
  }

  get clientInstanceId(): string {
    return this.clientInstanceIdValue;
  }

  get apiClientProvider(): ApiClient | null {
    return this.apiClient;
  }

  /** 是否存在已持久化的 refresh token（测试环境检测真实会话用）。 */
  async hasStoredRefreshToken(): Promise<boolean> {
    return (await this.session.loadRefreshToken()) !== null;
  }

  /** 测试注入：替换生产 HTTP 传输（仅 ohosTest 使用，不在生产调用）。 */
  setTransportForTesting(transport: HttpTransport | null): void {
    this.testTransport = transport;
  }

  /** 启动初始化：预生成 client_instance_id，恢复已存基址与会话。 */
  async initialize(context: common.Context): Promise<void> {
    this.context = context;
    this.clientInstanceIdValue = await this.loadClientInstanceId(context);
    const saved = await ServerProfileStore.load(context);
    if (saved === null) {
      this.status = AuthStatus.SERVER_REQUIRED;
      return;
    }
    await this.restoreProfile(saved);
  }

  /** 配置并保存后端基址；私网明文 http 需要确认。 */
  async configureServer(input: string): Promise<void> {
    const context = this.context;
    if (context === null) {
      return;
    }
    let normalized: string;
    try {
      normalized = ServerProfile.normalize(input, false);
    } catch (err) {
      if (err instanceof ServerAddressException &&
        err.code === ServerAddressCodes.PRIVATE_HTTP_CONFIRMATION_REQUIRED) {
        this.pendingPrivateHttp = input;
        return;
      }
      this.setError(err);
      return;
    }
    await this.applyServerChange(context, normalized);
  }

  /** 用户确认私网明文 http 后重试配置。 */
  async confirmPrivateHttp(): Promise<void> {
    const pending = this.pendingPrivateHttp;
    const context = this.context;
    this.pendingPrivateHttp = null;
    if (pending === null || context === null) {
      return;
    }
    try {
      const normalized = ServerProfile.normalize(pending, true);
      await this.applyServerChange(context, normalized);
    } catch (err) {
      this.setError(err);
    }
  }

  cancelPrivateHttp(): void {
    this.pendingPrivateHttp = null;
  }

  /** 提交 bootstrap 初始化口令（X-Bootstrap-Token 单次携带）。 */
  async submitBootstrap(token: string, username: string, password: string): Promise<void> {
    const client = this.requireClient();
    this.busy = true;
    this.clearError();
    try {
      const pair = await client.bootstrap(token, username, password, this.clientInstanceIdValue);
      this.enterAuthenticated(pair);
    } catch (err) {
      this.setError(err);
    } finally {
      this.busy = false;
    }
  }

  /** 提交登录。 */
  async submitLogin(username: string, password: string): Promise<void> {
    const client = this.requireClient();
    this.busy = true;
    this.clearError();
    try {
      const pair = await client.login(username, password, this.clientInstanceIdValue);
      this.enterAuthenticated(pair);
    } catch (err) {
      this.setError(err);
    } finally {
      this.busy = false;
    }
  }

  /** 退出：尽力注销旧会话 + 清本机令牌/字幕缓存/事件状态。 */
  async logout(): Promise<void> {
    if (this.eventClient !== null) {
      this.eventClient.stop();
      this.eventClient = null;
    }
    this.snapshot = null;
    if (this.apiClient !== null) {
      try {
        await this.apiClient.logout();
      } catch (err) {
        // 旧服务端不可达：仍继续清本地
      }
    }
    this.apiClient = null;
    await this.session.clearTokens();
    const context = this.context;
    if (context !== null) {
      await SubtitleCache.clear(context);
      // GFriends 临时图片缓存（cacheDir/gfriends-v1 证明式清理）
      await gfriendsCache.clear();
    }
    // 认证目录图片内存缓存（退出登录后不得复用旧会话图片）
    catalogImageCache.clear();
    this.status = this.serverBaseUrl.length > 0 ? AuthStatus.UNAUTHENTICATED : AuthStatus.SERVER_REQUIRED;
  }

  // ---- 内部 ----

  private async restoreProfile(savedBaseUrl: string): Promise<void> {
    this.serverBaseUrl = savedBaseUrl;
    const context = this.context;
    if (context === null) {
      this.status = AuthStatus.SERVER_REQUIRED;
      return;
    }
    this.buildClient(savedBaseUrl);
    const refreshToken = await this.session.loadRefreshToken();
    if (refreshToken === null) {
      this.status = AuthStatus.UNAUTHENTICATED;
      return;
    }
    // 有 refresh token：静默恢复
    const client = this.requireClient();
    try {
      const pair = await client.refresh();
      this.enterAuthenticated(pair);
    } catch (err) {
      this.status = AuthStatus.UNAUTHENTICATED;
      this.setError(err);
    }
  }

  private async applyServerChange(context: common.Context, normalized: string): Promise<void> {
    const oldBaseUrl = this.serverBaseUrl;
    if (oldBaseUrl.length > 0 && oldBaseUrl !== normalized) {
      // 更换地址：尽力注销旧服务端会话并清本地
      await this.logout();
    }
    await ServerProfileStore.save(context, normalized);
    this.serverBaseUrl = normalized;
    this.bootstrapRequired = false;
    this.buildClient(normalized);
    // 探测服务端初始化状态
    const client = this.requireClient();
    try {
      const status = await client.getBootstrapStatus();
      this.bootstrapRequired = !status.initialized;
    } catch (err) {
      this.setError(err);
    }
    this.status = AuthStatus.UNAUTHENTICATED;
  }

  private buildClient(baseUrl: string): void {
    const transport = this.testTransport !== null ? this.testTransport : new NetworkHttpTransport();
    this.apiClient = new ApiClient(transport, `${baseUrl}/api/v1`, this.session);
  }

  private enterAuthenticated(pair: TokenPair): void {
    this.bootstrapRequired = false;
    this.status = AuthStatus.AUTHENTICATED;
    this.startEvents();
  }

  /** 认证后启动事件连接：快照恢复 + WebSocket。 */
  private startEvents(): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    this.snapshot = new SnapshotStore(client);
    const transport: WebSocketTransport = new NetworkWebSocketTransport();
    this.eventClient = new EventClient(transport, client, this.snapshot);
    this.eventClient.start().catch((_err: Error) => {
      // 事件连接失败不阻塞登录态；EventClient 内部会退避重连
    });
  }

  private requireClient(): ApiClient {
    if (this.apiClient === null) {
      throw new ApiException('client_protocol_error', 0, '', '客户端未初始化', null);
    }
    return this.apiClient;
  }

  private async loadClientInstanceId(context: common.Context): Promise<string> {
    const store = await preferences.getPreferences(context, 'sakuraplayer_settings');
    const existing = await store.get('installation.client_instance_id', '') as string;
    if (existing.length === 36) {
      return existing;
    }
    const generated = util.generateRandomUUID();
    await store.put('installation.client_instance_id', generated);
    await store.flush();
    return generated;
  }

  private setError(err: Object): void {
    if (err instanceof ServerAddressException) {
      this.errorCode = err.code;
      this.errorMessage = err.message;
      return;
    }
    if (err instanceof ApiException) {
      this.errorCode = err.code;
      this.errorMessage = err.message;
      return;
    }
    this.errorCode = 'client_unknown_error';
    this.errorMessage = '未知错误';
  }

  private clearError(): void {
    this.errorCode = null;
    this.errorMessage = null;
  }
}

/** 全局认证单例。 */
export const authStore = new AuthStore();
