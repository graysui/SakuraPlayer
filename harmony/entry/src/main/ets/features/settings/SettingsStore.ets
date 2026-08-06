/**
 * 设置页 Store（AC-094/119/120/121）。
 *
 * - TTL 1..168 步进输入；保存只 PATCH cache_ttl_hours，成功用响应真相，失败保留输入。
 * - JavDB/AI/MGDB 对象级 replace/clear CAS（expected_version）；密码/API key 只回显
 *   configured；state_conflict 后重新加载（不自动用旧输入覆盖新版本）。
 * - 连接测试 5 目标，在途禁用；错误码中文映射（未知码显示"未知错误"）。
 * - MGDB 立即全量同步（202 创建/复用）；同步状态只读展示。
 * - 主密钥（启动级 master key）不可编辑：本页不提供任何 master key 控件。
 */

import { ApiClient } from '../../core/api/ApiClient';
import { ApiException, ConnectionTest, Settings } from '../../core/api/ApiModels';

export enum SettingsStatus {
  IDLE,
  LOADING,
  READY,
  FAILED,
}

@ObservedV2
export class SettingsStore {
  @Trace status: SettingsStatus = SettingsStatus.IDLE;
  @Trace settings: Settings | null = null;
  @Trace errorMessage: string | null = null;
  // 用户输入（TTL/CAS 表单）
  @Trace ttlInput: number = 24;
  @Trace javdbUsername: string = '';
  @Trace javdbPassword: string = '';
  @Trace aiBaseUrl: string = '';
  @Trace aiModel: string = '';
  @Trace aiTimeout: string = '';
  @Trace aiApiKey: string = '';
  @Trace mgdbSourceUrl: string = '';
  @Trace savingTtl: boolean = false;
  @Trace savingJavdb: boolean = false;
  @Trace savingAi: boolean = false;
  @Trace savingMgdb: boolean = false;
  @Trace testingTarget: string | null = null;
  connectionResults: Map<string, ConnectionTest> = new Map();
  @Trace syncingMgdb: boolean = false;
  @Trace mgdbSyncFeedback: string | null = null;

  private apiClient: ApiClient | null = null;
  private generation: number = 0;
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

  detach(): void {
    this.apiClient = null;
    this.generation++;
    this.status = SettingsStatus.IDLE;
    this.settings = null;
    this.errorMessage = null;
    this.savingTtl = false;
    this.savingJavdb = false;
    this.savingAi = false;
    this.savingMgdb = false;
    this.testingTarget = null;
    this.syncingMgdb = false;
    // 离开页面清空秘密输入（契约：离开时清空输入 controller）
    this.javdbPassword = '';
    this.aiApiKey = '';
  }

  load(): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = ++this.generation;
    this.status = SettingsStatus.LOADING;
    this.errorMessage = null;
    this.notifyChanged();
    client.getSettings().then((settings: Settings) => {
      if (gen !== this.generation) {
        return;
      }
      this.settings = settings;
      this.ttlInput = settings.cacheTtlHours;
      // 回显非秘密现值（AC-119）：密码/API key 只显示 configured
      this.javdbUsername = settings.javdb.username ?? '';
      this.aiBaseUrl = settings.ai.baseUrl ?? '';
      this.aiModel = settings.ai.model ?? '';
      this.aiTimeout = settings.ai.timeoutSeconds === null ? '' : `${settings.ai.timeoutSeconds}`;
      this.mgdbSourceUrl = settings.mgdb.sourceUrl ?? '';
      this.status = SettingsStatus.READY;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.status = SettingsStatus.FAILED;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  retry(): void {
    this.load();
  }

  setTtlInput(value: number): void {
    this.ttlInput = value;
  }

  /** 保存 TTL：范围 1..168；成功用响应真相，失败保留输入并显示错误。 */
  saveTtl(): void {
    const client = this.apiClient;
    if (client === null || this.savingTtl) {
      return;
    }
    const value = Math.round(this.ttlInput);
    if (value < 1 || value > 168) {
      this.errorMessage = '缓存期限需在 1 至 168 小时之间';
      this.notifyChanged();
      return;
    }
    const gen = this.generation;
    this.savingTtl = true;
    this.errorMessage = null;
    this.notifyChanged();
    const body = `{"cache_ttl_hours":${value}}`;
    client.updateSettings(body).then((settings: Settings) => {
      if (gen !== this.generation) {
        return;
      }
      this.settings = settings;
      this.ttlInput = settings.cacheTtlHours;
      this.savingTtl = false;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.savingTtl = false;
      if (this.errorCodeOf(err) === 'state_conflict') {
        this.errorMessage = '数据已变化，请刷新后重试';
        this.load();
        return;
      }
      this.errorMessage = this.errorTextOf(err);
      // 失败保留服务端确认前值与用户输入（不重载覆盖输入）
      this.notifyChanged();
    });
  }

  /** JavDB replace（对象级 CAS）。 */
  saveJavdb(): void {
    const settings = this.settings;
    const client = this.apiClient;
    if (client === null || settings === null || this.savingJavdb) {
      return;
    }
    const body = `{"javdb":{"action":"replace","expected_version":${settings.javdb.version},` +
      `"username":${JSON.stringify(this.javdbUsername)},` +
      `"password":${JSON.stringify(this.javdbPassword)}}}`;
    this.applyCasPatch(body, 'javdb');
  }

  clearJavdb(): void {
    const settings = this.settings;
    if (settings === null || settings.javdb.version < 1) {
      return;
    }
    const body = `{"javdb":{"action":"clear","expected_version":${settings.javdb.version}}}`;
    this.applyCasPatch(body, 'javdb');
  }

  /** AI replace（base_url/model/timeout/api_key）。 */
  saveAi(): void {
    const settings = this.settings;
    const client = this.apiClient;
    if (client === null || settings === null || this.savingAi) {
      return;
    }
    const timeout = this.aiTimeout.length > 0 ? Number(this.aiTimeout) : null;
    const body = `{"ai":{"action":"replace","expected_version":${settings.ai.version},` +
      `"base_url":${JSON.stringify(this.aiBaseUrl)},"model":${JSON.stringify(this.aiModel)},` +
      `"timeout_seconds":${timeout === null ? 'null' : timeout},` +
      `"api_key":${JSON.stringify(this.aiApiKey)}}}`;
    this.applyCasPatch(body, 'ai');
  }

  clearAi(): void {
    const settings = this.settings;
    if (settings === null || settings.ai.version < 1) {
      return;
    }
    const body = `{"ai":{"action":"clear","expected_version":${settings.ai.version}}}`;
    this.applyCasPatch(body, 'ai');
  }

  /** MGDB replace（source_url 仅 GitHub HTTPS 仓库）。 */
  saveMgdb(): void {
    const settings = this.settings;
    if (settings === null || this.savingMgdb) {
      return;
    }
    const url = this.mgdbSourceUrl.trim();
    if (!SettingsStore.isGithubSourceUrl(url)) {
      this.errorMessage = 'MGDB 数据源需为 GitHub HTTPS 仓库地址';
      this.notifyChanged();
      return;
    }
    const body = `{"mgdb":{"action":"replace","expected_version":${settings.mgdb.version},` +
      `"source_url":${JSON.stringify(url)}}}`;
    this.applyCasPatch(body, 'mgdb');
  }

  clearMgdb(): void {
    const settings = this.settings;
    if (settings === null || settings.mgdb.version < 1) {
      return;
    }
    const body = `{"mgdb":{"action":"clear","expected_version":${settings.mgdb.version}}}`;
    this.applyCasPatch(body, 'mgdb');
  }

  /** 连接测试：单目标在途，只读 probe。 */
  testConnection(target: string): void {
    const client = this.apiClient;
    if (client === null || this.testingTarget !== null) {
      return;
    }
    const gen = this.generation;
    this.testingTarget = target;
    this.notifyChanged();
    client.testConnection(target).then((test: ConnectionTest) => {
      if (gen !== this.generation) {
        return;
      }
      this.connectionResults.set(target, test);
      this.testingTarget = null;
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.testingTarget = null;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  /** MGDB 立即全量同步（202 创建/复用）。 */
  requestFullSync(): void {
    const client = this.apiClient;
    if (client === null || this.syncingMgdb) {
      return;
    }
    const gen = this.generation;
    this.syncingMgdb = true;
    this.mgdbSyncFeedback = null;
    this.notifyChanged();
    client.requestMgdbFullSync().then(() => {
      if (gen !== this.generation) {
        return;
      }
      this.syncingMgdb = false;
      this.mgdbSyncFeedback = '全量同步请求已提交';
      this.load();
      this.notifyChanged();
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.syncingMgdb = false;
      this.errorMessage = this.errorTextOf(err);
      this.notifyChanged();
    });
  }

  private applyCasPatch(body: string, kind: string): void {
    const client = this.apiClient;
    if (client === null) {
      return;
    }
    const gen = this.generation;
    if (kind === 'javdb') {
      this.savingJavdb = true;
    } else if (kind === 'ai') {
      this.savingAi = true;
    } else {
      this.savingMgdb = true;
    }
    this.errorMessage = null;
    this.notifyChanged();
    client.updateSettings(body).then((settings: Settings) => {
      if (gen !== this.generation) {
        return;
      }
      this.settings = settings;
      this.clearInputs(kind);
      this.clearSaving(kind);
      this.notifyChanged();
      if (kind === 'ai') {
        // AI replace/clear 成功后必须再执行一次权威 GET /settings
        this.load();
      }
    }).catch((err: Error) => {
      if (gen !== this.generation) {
        return;
      }
      this.clearSaving(kind);
      this.errorMessage = this.errorTextOf(err);
      if (this.errorCodeOf(err) === 'state_conflict') {
        // 数据已变化：重新加载权威版本，不自动用旧输入覆盖
        this.errorMessage = '数据已变化，请刷新后重试';
        this.load();
        return;
      }
      this.notifyChanged();
    });
  }

  private clearInputs(kind: string): void {
    if (kind === 'javdb') {
      this.javdbPassword = '';
    } else if (kind === 'ai') {
      this.aiApiKey = '';
    }
  }

  private clearSaving(kind: string): void {
    if (kind === 'javdb') {
      this.savingJavdb = false;
    } else if (kind === 'ai') {
      this.savingAi = false;
    } else {
      this.savingMgdb = false;
    }
  }

  private errorCodeOf(err: Error): string {
    if (err instanceof ApiException) {
      return err.code;
    }
    return 'client_transport_error';
  }

  errorTextOf(err: Error): string {
    const code = this.errorCodeOf(err);
    if (code === 'state_conflict') {
      return '数据已变化，请刷新后重试';
    }
    if (code === 'invalid_source_url') {
      return 'MGDB 数据源地址不合法';
    }
    if (code === 'client_transport_error') {
      return '无法连接服务器，请稍后重试';
    }
    return '操作失败，请重试';
  }

  /** 连接测试结果中文文案（未知码显示"未知错误"）。 */
  static connectionStatusText(test: ConnectionTest | undefined): string {
    if (test === undefined) {
      return '未测试';
    }
    if (test.status === 'available') {
      return '连接正常';
    }
    if (test.status === 'credentials_invalid') {
      return '凭据无效';
    }
    if (test.status === 'not_configured') {
      return '未配置';
    }
    return '连接失败';
  }

  static connectionErrorText(test: ConnectionTest): string {
    const code = test.errorCode;
    if (code === null) {
      return '';
    }
    if (code === 'cloud115_unavailable') {
      return '115 暂时不可用';
    }
    if (code === 'cloud115_credentials_expired') {
      return '115 凭据已失效';
    }
    if (code === 'javdb_credentials_invalid') {
      return 'JavDB 凭据无效';
    }
    if (code === 'upstream_unavailable') {
      return '上游站点不可用';
    }
    if (code === 'ai_api_key_invalid') {
      return 'AI API Key 无效';
    }
    return '未知错误';
  }

  static syncStateTextSafe(status: string): string {
    if (status === 'never') {
      return '从未运行';
    }
    if (status === 'running') {
      return '同步中';
    }
    if (status === 'succeeded') {
      return '同步成功';
    }
    if (status === 'failed') {
      return '同步失败';
    }
    return status;
  }

  static isGithubSourceUrl(url: string): boolean {
    if (!url.startsWith('https://')) {
      return false;
    }
    if (url.includes('@') || url.includes('?') || url.includes('#')) {
      return false;
    }
    const rest = url.substring('https://'.length);
    if (rest.startsWith('github.com/')) {
      const segments = rest.split('/');
      return segments.length === 3 && segments[1].length > 0 && segments[2].length > 0;
    }
    if (rest.startsWith('api.github.com/repos/')) {
      const segments = rest.split('/');
      return segments.length === 4 && segments[2].length > 0 && segments[3].length > 0;
    }
    return false;
  }

  private notifyChanged(): void {
    for (const listener of this.changeListeners) {
      listener();
    }
  }
}
