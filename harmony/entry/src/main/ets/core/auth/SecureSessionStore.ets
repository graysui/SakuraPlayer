/**
 * 会话安全存储：refresh token 存 Asset Store Kit，access token 仅驻内存。
 *
 * AC-011/AC-012：明文密码不落盘；刷新令牌只进 Asset Store（系统安全环境）；
 * 任何凭据不写入 Preferences 或日志。logout 时删除令牌与字幕缓存（由 AuthStore 协调）。
 */

import { asset } from '@kit.AssetStoreKit';
import { util } from '@kit.ArkTS';
import { SessionProvider } from '../api/ApiClient';
import { TokenPair } from '../api/ApiModels';

/** 常量导入别名（ArkTS 无命名空间冲突时直接使用 asset.Tag）。 */
const REFRESH_ALIAS = 'sakuraplayer.refresh_token';

/**
 * 内存会话 + Asset Store refresh token。
 * 测试可注入 FakeAssetStore 以避免依赖真实系统安全环境。
 */
export interface SecretStore {
  write(alias: string, secret: string): Promise<void>;
  read(alias: string): Promise<string | null>;
  remove(alias: string): Promise<void>;
}

/** 生产实现：Asset Store Kit。 */
export class AssetSecretStore implements SecretStore {
  async write(alias: string, secret: string): Promise<void> {
    // 覆盖写：先删后加，忽略不存在错误
    try {
      await asset.remove(this.aliasMap(alias));
    } catch (err) {
      // 不存在时忽略
    }
    const attributes: asset.AssetMap = new Map();
    attributes.set(asset.Tag.ALIAS, this.toBytes(alias));
    attributes.set(asset.Tag.SECRET, this.toBytes(secret));
    await asset.add(attributes);
  }

  async read(alias: string): Promise<string | null> {
    let result: Array<asset.AssetMap>;
    try {
      result = await asset.query(this.aliasMap(alias));
    } catch (err) {
      return null;
    }
    if (result.length === 0) {
      return null;
    }
    const secret = result[0].get(asset.Tag.SECRET);
    if (secret === undefined || !(secret instanceof Uint8Array)) {
      return null;
    }
    return this.fromBytes(secret as Uint8Array);
  }

  async remove(alias: string): Promise<void> {
    try {
      await asset.remove(this.aliasMap(alias));
    } catch (err) {
      // 不存在时忽略
    }
  }

  private aliasMap(alias: string): asset.AssetMap {
    const map: asset.AssetMap = new Map();
    map.set(asset.Tag.ALIAS, this.toBytes(alias));
    return map;
  }

  private toBytes(text: string): Uint8Array {
    return new util.TextEncoder().encodeInto(text);
  }

  private fromBytes(bytes: Uint8Array): string {
    return new util.TextDecoder().decodeWithStream(bytes);
  }
}

/** SecureSessionStore：内存 access/refresh token + SecretStore 持久化 refresh token。 */
export class SecureSessionStore implements SessionProvider {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private readonly secretStore: SecretStore;

  constructor(secretStore: SecretStore = new AssetSecretStore()) {
    this.secretStore = secretStore;
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  getRefreshToken(): string | null {
    return this.refreshToken;
  }

  /** 冷启动时从 Asset Store 恢复 refresh token 到内存（用于静默恢复会话）。 */
  async loadRefreshToken(): Promise<string | null> {
    this.refreshToken = await this.secretStore.read(REFRESH_ALIAS);
    return this.refreshToken;
  }

  async setTokens(pair: TokenPair): Promise<void> {
    this.accessToken = pair.accessToken;
    this.refreshToken = pair.refreshToken;
    await this.secretStore.write(REFRESH_ALIAS, pair.refreshToken);
  }

  async clearTokens(): Promise<void> {
    this.accessToken = null;
    this.refreshToken = null;
    await this.secretStore.remove(REFRESH_ALIAS);
  }
}
