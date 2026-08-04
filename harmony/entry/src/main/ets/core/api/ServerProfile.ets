/**
 * 后端基址（api_base_url）规范化、持久化与连接测试。
 *
 * 契约（runtime-configuration.md / AC-135）：
 * - 绝对 http/https；禁 userinfo、query、fragment、路径。
 * - http 仅允许 loopback 或 RFC1918/ULA/link-local 私有地址，并要求一次明确确认；
 *   公网明文 http 直接拒绝。https 走系统信任链，无忽略证书开关。
 * - 基址作为非敏感本机设置保存于 Preferences。
 */

import { preferences } from '@kit.ArkData';
import { url } from '@kit.ArkTS';
import { common } from '@kit.AbilityKit';
import { ApiClient, NetworkHttpTransport, SessionProvider } from './ApiClient';
import { BootstrapStatus } from './ApiModels';

/** 地址策略异常：code 为稳定错误码。 */
export class ServerAddressException extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

/** 基址策略错误码。 */
export class ServerAddressCodes {
  static readonly INVALID_URL = 'server_url_invalid';
  static readonly UNSUPPORTED_SCHEME = 'server_scheme_unsupported';
  static readonly USERINFO_FORBIDDEN = 'server_userinfo_forbidden';
  static readonly PATH_FORBIDDEN = 'server_path_forbidden';
  static readonly QUERY_FORBIDDEN = 'server_query_fragment_forbidden';
  static readonly PUBLIC_HTTP_FORBIDDEN = 'public_http_forbidden';
  static readonly PRIVATE_HTTP_CONFIRMATION_REQUIRED = 'private_http_confirmation_required';
  static readonly API_VERSION_UNSUPPORTED = 'server_api_version_unsupported';
}

export class ServerProfile {
  /**
   * 规范化后端基址。
   * @param input 用户输入地址
   * @param allowPrivateHttp 是否已确认私网明文 http
   * @returns 规范化后的 scheme://host[:port]
   */
  static normalize(input: string, allowPrivateHttp: boolean): string {
    const trimmed = input.trim();
    if (trimmed.length === 0) {
      throw new ServerAddressException(ServerAddressCodes.INVALID_URL, '地址不能为空');
    }
    let parsed: url.URL;
    try {
      parsed = url.URL.parseURL(trimmed);
    } catch (err) {
      throw new ServerAddressException(ServerAddressCodes.INVALID_URL, '地址格式非法');
    }
    const scheme = parsed.protocol.toLowerCase();
    if (scheme !== 'http:' && scheme !== 'https:') {
      throw new ServerAddressException(ServerAddressCodes.UNSUPPORTED_SCHEME, '仅支持 http/https');
    }
    const hostname = parsed.hostname.toLowerCase();
    if (hostname.length === 0) {
      throw new ServerAddressException(ServerAddressCodes.INVALID_URL, '缺少主机名');
    }
    if (parsed.username.length > 0 || parsed.password.length > 0) {
      throw new ServerAddressException(ServerAddressCodes.USERINFO_FORBIDDEN, '地址不得包含用户信息');
    }
    if (parsed.pathname.length > 0 && parsed.pathname !== '/') {
      throw new ServerAddressException(ServerAddressCodes.PATH_FORBIDDEN, '地址不得包含路径');
    }
    if (parsed.search.length > 0 || parsed.hash.length > 0) {
      throw new ServerAddressException(ServerAddressCodes.QUERY_FORBIDDEN, '地址不得包含查询或片段');
    }

    const port = parsed.port.length > 0 ? `:${parsed.port}` : '';
    const origin = `${scheme}//${hostname}${port}`;

    if (scheme === 'http:') {
      if (!ServerProfile.isLoopback(hostname) && !ServerProfile.isPrivateLiteral(hostname)) {
        throw new ServerAddressException(ServerAddressCodes.PUBLIC_HTTP_FORBIDDEN, '公网明文 HTTP 不允许');
      }
      if (!allowPrivateHttp && !ServerProfile.isLoopback(hostname)) {
        throw new ServerAddressException(
          ServerAddressCodes.PRIVATE_HTTP_CONFIRMATION_REQUIRED, '私网明文 HTTP 需要风险确认');
      }
    }
    return origin;
  }

  /** loopback：127.0.0.0/8、::1、localhost。 */
  static isLoopback(hostname: string): boolean {
    if (hostname === 'localhost') {
      return true;
    }
    if (hostname.startsWith('::1')) {
      return true;
    }
    if (hostname.startsWith('127.')) {
      return ServerProfile.isIpv4Literal(hostname);
    }
    return false;
  }

  /** RFC1918 IPv4 / IPv6 ULA、link-local。 */
  static isPrivateLiteral(hostname: string): boolean {
    if (hostname.startsWith('10.')) {
      return ServerProfile.isIpv4Literal(hostname);
    }
    if (hostname.startsWith('192.168.')) {
      return ServerProfile.isIpv4Literal(hostname);
    }
    if (hostname.startsWith('169.254.')) {
      return ServerProfile.isIpv4Literal(hostname);
    }
    if (hostname.startsWith('172.')) {
      if (!ServerProfile.isIpv4Literal(hostname)) {
        return false;
      }
      const second = Number.parseInt(hostname.split('.')[1], 10);
      return second >= 16 && second <= 31;
    }
    // IPv6：ULA fc00::/7 与 link-local fe80::/10（必须是 IPv6 字面量，含冒号）
    if (hostname.includes(':')) {
      if (hostname.startsWith('fc') || hostname.startsWith('fd')) {
        return true;
      }
      if (hostname.startsWith('fe8') || hostname.startsWith('fe9') ||
        hostname.startsWith('fea') || hostname.startsWith('feb')) {
        return true;
      }
    }
    return false;
  }

  private static isIpv4Literal(hostname: string): boolean {
    const parts = hostname.split('.');
    if (parts.length !== 4) {
      return false;
    }
    for (const part of parts) {
      if (part.length === 0 || part.length > 3) {
        return false;
      }
      for (let i = 0; i < part.length; i++) {
        const ch = part.charCodeAt(i);
        if (ch < 48 || ch > 57) {
          return false;
        }
      }
      const value = Number.parseInt(part, 10);
      if (value < 0 || value > 255) {
        return false;
      }
    }
    return true;
  }
}

/** 基址 Preferences 持久化（非敏感设置）。 */
export class ServerProfileStore {
  private static readonly PREF_NAME = 'sakuraplayer_settings';
  private static readonly KEY_BASE_URL = 'api_base_url';

  static async load(context: common.Context): Promise<string | null> {
    try {
      const store = await preferences.getPreferences(context, ServerProfileStore.PREF_NAME);
      const value = await store.get(ServerProfileStore.KEY_BASE_URL, '') as string;
      return value.length > 0 ? value : null;
    } catch (err) {
      // 读取失败按未配置处理
      return null;
    }
  }

  static async save(context: common.Context, baseUrl: string): Promise<void> {
    try {
      const store = await preferences.getPreferences(context, ServerProfileStore.PREF_NAME);
      await store.put(ServerProfileStore.KEY_BASE_URL, baseUrl);
      await store.flush();
    } catch (err) {
      throw new ServerAddressException(ServerAddressCodes.INVALID_URL, '基址保存失败');
    }
  }

  static async clear(context: common.Context): Promise<void> {
    try {
      const store = await preferences.getPreferences(context, ServerProfileStore.PREF_NAME);
      await store.delete(ServerProfileStore.KEY_BASE_URL);
      await store.flush();
    } catch (err) {
      // 清理失败不影响会话退出
    }
  }
}

/** 连接测试：GET /auth/bootstrap-status 且 api_version==1。 */
export class ServerConnectionTester {
  /**
   * @returns BootstrapStatus（api_version 已校验为 1）
   * @throws ServerAddressException(API_VERSION_UNSUPPORTED) 或 ApiException
   */
  static async test(baseUrl: string, session: SessionProvider): Promise<BootstrapStatus> {
    const client = new ApiClient(new NetworkHttpTransport(10000, 10000), `${baseUrl}/api/v1`, session);
    const status = await client.getBootstrapStatus();
    if (status.apiVersion !== 1) {
      throw new ServerAddressException(ServerAddressCodes.API_VERSION_UNSUPPORTED, '服务端 API 版本不受支持');
    }
    return status;
  }
}
