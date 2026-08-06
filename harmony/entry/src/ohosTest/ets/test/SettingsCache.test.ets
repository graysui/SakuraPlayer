/**
 * TASK-308 设置/缓存/诊断 Store 测试：
 * - QR 状态机：waiting 轮询、confirmed 一次 confirm、expired/canceled 清会话重扫、
 *   credentials_expired 与 unavailable 文案分离、PNG 内存生命周期
 * - Settings DTO：TTL 边界、固定容量 20/3/600、CAS 字段不回显密码
 * - CacheStore：取消 {confirmed:true} 202 替换、清理、active_lease 拒绝保留
 * - DiagnosticsStore：暂停/恢复、富化重试、组件状态文案
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { CacheJobDetail, TokenPair } from '../../../main/ets/core/api/ApiModels';
import { QrBindingStatus, QrBindingStore } from '../../../main/ets/features/settings/QrBindingStore';
import { SettingsStatus, SettingsStore } from '../../../main/ets/features/settings/SettingsStore';
import { CachePageStatus, CacheStore } from '../../../main/ets/features/cache/CacheStore';
import { DiagnosticsStatus, DiagnosticsStore } from '../../../main/ets/features/settings/DiagnosticsStore';

class FakeSession implements SessionProvider {
  getAccessToken(): string | null {
    return 'fake-access';
  }

  getRefreshToken(): string | null {
    return 'fake-refresh';
  }

  setTokens(pair: TokenPair): Promise<void> {
    return Promise.resolve();
  }

  clearTokens(): Promise<void> {
    return Promise.resolve();
  }
}

class FakeHttpTransport implements HttpTransport {
  routes: Map<string, HttpResponse> = new Map();
  requests: HttpRequest[] = [];

  request(request: HttpRequest): Promise<HttpResponse> {
    this.requests.push(request);
    const hit = this.routes.get(request.url);
    if (hit === undefined) {
      return Promise.reject(new Error(`no route for ${request.url}`));
    }
    return Promise.resolve(hit);
  }
}

const BASE = 'http://test/api/v1';
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

function bindingBody(bound: boolean, status: string, displayName: string | null): string {
  return `{"bound":${bound},"status":"${status}","display_name":${displayName === null ? 'null' : `"${displayName}"`},"cache_root_ready":true,"last_verified_at":"2026-08-06T00:00:00Z"}`;
}

function qrBody(status: string, png: string | null): string {
  return `{"id":"10000000-0000-0000-0000-000000000001","status":"${status}",` +
    `"qrcode_png_base64":${png === null ? 'null' : `"${png}"`},"expires_at":"2026-08-06T00:30:00Z"}`;
}

function settingsBody(ttl: number): string {
  return `{"cache_ttl_hours":${ttl},"ready_cache_limit":20,"metadata_concurrency":3,` +
    `"metadata_timeout_seconds":600,` +
    `"javdb":{"configured":true,"status":"available","last_checked_at":"2026-08-06T00:00:00Z","last_error_code":null,"username":"user1","password_configured":true,"version":2},` +
    `"ai":{"configured":true,"status":"available","last_checked_at":"2026-08-06T00:00:00Z","last_error_code":null,"base_url":"https://api.example.com/v1","model":"qwen","timeout_seconds":60,"api_key_configured":true,"version":1},` +
    `"mgdb":{"configured":true,"source_url":"https://github.com/owner/repo","version":3},` +
    `"providers":{"cloud115":{"configured":true,"status":"available","last_checked_at":"2026-08-06T00:00:00Z","last_error_code":null},"dmm":{"configured":true,"status":"available","last_checked_at":"2026-08-06T00:00:00Z","last_error_code":null}},` +
    `"avdb_sync":{"incremental_30d":{"status":"succeeded","imported_count":120,"release_id":null,"last_successful_at":"2026-08-06T00:00:00Z","next_scheduled_at":null},"full_reconcile":{"status":"never","imported_count":0,"release_id":null,"last_successful_at":null,"next_scheduled_at":null}}}`;
}

function cacheJobBody(id: string, status: string): string {
  return `{"id":"${id}","movie_id":"10000000-0000-0000-0000-0000000000a1","source_id":"10000000-0000-0000-0000-0000000000b1",` +
    `"status":"${status}","remote_percent":null,"error_code":null,"media_candidates":[],"selected_media_ids":[],` +
    `"subtitles":[],"ready_at":null,"expires_at":null,"created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"}`;
}

function cachePageBody(items: string, running: number, queued: number, ready: number): string {
  return `{"items":[${items}],"capacity":{"running":${running},"running_limit":2,"queued":${queued},"queued_limit":10,"ready":${ready},"ready_limit":20},"next_cursor":null}`;
}

function diagnosticsBody(): string {
  return `{"generated_at":"2026-08-06T00:00:00Z",` +
    `"components":[{"component":"api","status":"healthy","error_code":null,"checked_at":"2026-08-06T00:00:00Z"},{"component":"worker","status":"degraded","error_code":"slow","checked_at":"2026-08-06T00:00:00Z"}],` +
    `"queues":{"metadata_queued":2,"metadata_running":1,"metadata_paused":false,"cache_queued":3,"cache_running":1,"cache_ready":4},` +
    `"metadata_progress":{"total":10,"queued":2,"running":1,"completed":6,"failed":1,"finished":7,"current_numbers":["ABC-123"]},` +
    `"recent_failures":[{"task_type":"metadata","task_id":"10000000-0000-0000-0000-0000000000e1","error_code":"scrape_failed","attempt_no":2,"elapsed_ms":5000,"occurred_at":"2026-08-06T00:00:00Z"}],` +
    `"connection_tests":[{"target":"cloud115","status":"available","error_code":null,"elapsed_ms":80,"checked_at":"2026-08-06T00:00:00Z"}]}`;
}

class QrFixture {
  readonly transport: FakeHttpTransport;
  readonly store: QrBindingStore;

  constructor() {
    this.transport = new FakeHttpTransport();
    const client = new ApiClient(this.transport, BASE, new FakeSession());
    this.store = new QrBindingStore(10);
    this.store.attach(client);
  }
}

class StoreFixture {
  readonly transport: FakeHttpTransport;
  readonly client: ApiClient;

  constructor() {
    this.transport = new FakeHttpTransport();
    this.client = new ApiClient(this.transport, BASE, new FakeSession());
  }
}

export default function settingsCacheTest() {
  describe('QrBindingStore', () => {
    it('creates_session_and_polls_waiting_then_confirmed_once', 0, async () => {
      const fixture = new QrFixture();
      fixture.transport.routes.set(`${BASE}/cloud115/binding`, { statusCode: 200, body: bindingBody(false, 'unbound', null) });
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions`, { statusCode: 201, body: qrBody('waiting', PNG) });
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions/10000000-0000-0000-0000-000000000001`, { statusCode: 200, body: qrBody('confirmed', null) });
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions/10000000-0000-0000-0000-000000000001/confirm`, { statusCode: 200, body: bindingBody(true, 'active', '账号A') });
      fixture.store.loadBinding();
      await sleep(30);
      const binding0 = fixture.store.binding;
      expect(binding0 !== null && !binding0.bound).assertTrue();
      fixture.store.startQr();
      await sleep(60);
      // 快速轮询下创建态瞬时存在；最终态为 CONFIRMED 且会话/PNG 已清空（内存生命周期）
      expect(fixture.store.status).assertEqual(QrBindingStatus.CONFIRMED);
      const binding1 = fixture.store.binding;
      expect(binding1 !== null && binding1.bound).assertTrue();
      expect(fixture.store.qrPngBase64).assertNull();
      expect(fixture.store.sessionId).assertNull();
      const confirms = fixture.transport.requests.filter((r) => r.url.includes('/confirm')).length;
      expect(confirms).assertEqual(1);
    });

    it('expired_session_clears_and_shows_rescan', 0, async () => {
      const fixture = new QrFixture();
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions`, { statusCode: 201, body: qrBody('expired', null) });
      fixture.store.startQr();
      await sleep(30);
      expect(fixture.store.status).assertEqual(QrBindingStatus.EXPIRED);
      expect(fixture.store.sessionId).assertNull();
      expect(fixture.store.qrPngBase64).assertNull();
    });

    it('credentials_expired_uses_separate_copy', 0, async () => {
      const fixture = new QrFixture();
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions`, { statusCode: 201, body: qrBody('waiting', PNG) });
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions/10000000-0000-0000-0000-000000000001`,
        { statusCode: 502, body: '{"code":"cloud115_credentials_expired","message":"expired","request_id":"r1"}' });
      fixture.store.startQr();
      await sleep(40);
      expect(fixture.store.status).assertEqual(QrBindingStatus.CREDENTIALS_EXPIRED);
      expect(fixture.store.errorMessage).assertEqual('凭据已失效，请重新扫码');
      expect(fixture.store.sessionId).assertNull();
    });

    it('unavailable_stops_polling_and_keeps_state', 0, async () => {
      const fixture = new QrFixture();
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions`, { statusCode: 201, body: qrBody('waiting', PNG) });
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions/10000000-0000-0000-0000-000000000001`,
        { statusCode: 503, body: '{"code":"cloud115_unavailable","message":"down","request_id":"r1"}' });
      fixture.store.startQr();
      await sleep(40);
      expect(fixture.store.status).assertEqual(QrBindingStatus.UNAVAILABLE);
      expect(fixture.store.errorMessage).assertEqual('115 暂时不可用，请稍后重试');
      const polls = fixture.transport.requests.filter((r) => r.url.includes('/qr-sessions/')).length;
      await sleep(40);
      const pollsAfter = fixture.transport.requests.filter((r) => r.url.includes('/qr-sessions/')).length;
      expect(pollsAfter).assertEqual(polls);
    });

    it('unbind_clears_session_and_binding', 0, async () => {
      const fixture = new QrFixture();
      fixture.transport.routes.set(`${BASE}/cloud115/binding`, { statusCode: 204, body: '' });
      fixture.store.unbind();
      await sleep(30);
      expect(fixture.store.unbinding).assertFalse();
      expect(fixture.store.binding).assertNull();
      expect(fixture.store.status).assertEqual(QrBindingStatus.IDLE);
    });

    it('detach_clears_all_qr_state', 0, async () => {
      const fixture = new QrFixture();
      fixture.transport.routes.set(`${BASE}/cloud115/qr-sessions`, { statusCode: 201, body: qrBody('waiting', PNG) });
      fixture.store.startQr();
      await sleep(30);
      fixture.store.detach();
      expect(fixture.store.sessionId).assertNull();
      expect(fixture.store.qrPngBase64).assertNull();
      expect(fixture.store.status).assertEqual(QrBindingStatus.IDLE);
    });
  });

  describe('SettingsStore', () => {
    it('loads_settings_and_fixed_limits', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 200, body: settingsBody(24) });
      const store = new SettingsStore();
      store.attach(fixture.client);
      store.load();
      await sleep(30);
      expect(store.status).assertEqual(SettingsStatus.READY);
      const settings = store.settings;
      expect(settings !== null).assertTrue();
      if (settings !== null) {
        expect(settings.cacheTtlHours).assertEqual(24);
        expect(settings.readyCacheLimit).assertEqual(20);
        expect(settings.metadataConcurrency).assertEqual(3);
        expect(settings.metadataTimeoutSeconds).assertEqual(600);
        expect(settings.javdb.passwordConfigured).assertTrue();
        expect(settings.javdb.username).assertEqual('user1');
        expect(settings.ai.apiKeyConfigured).assertTrue();
        expect(settings.mgdb.sourceUrl).assertEqual('https://github.com/owner/repo');
        expect(settings.avdbSync.incremental30d.status).assertEqual('succeeded');
        expect(settings.avdbSync.incremental30d.importedCount).assertEqual(120);
      }
      // 非秘密现值回显（AC-119）
      expect(store.javdbUsername).assertEqual('user1');
      expect(store.aiBaseUrl).assertEqual('https://api.example.com/v1');
      expect(store.aiModel).assertEqual('qwen');
      expect(store.aiTimeout).assertEqual('60');
      expect(store.mgdbSourceUrl).assertEqual('https://github.com/owner/repo');
    });

    it('ttl_out_of_range_is_rejected_locally', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 200, body: settingsBody(24) });
      const store = new SettingsStore();
      store.attach(fixture.client);
      store.load();
      await sleep(30);
      store.setTtlInput(200);
      store.saveTtl();
      await sleep(20);
      expect(store.errorMessage !== null).assertTrue();
      expect(fixture.transport.requests.length).assertEqual(1);
    });

    it('ttl_save_patches_and_uses_response_truth', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 200, body: settingsBody(24) });
      const store = new SettingsStore();
      store.attach(fixture.client);
      store.load();
      await sleep(30);
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 200, body: settingsBody(48) });
      store.setTtlInput(48);
      store.saveTtl();
      await sleep(30);
      const ttlSettings = store.settings;
      expect(ttlSettings !== null && ttlSettings.cacheTtlHours).assertEqual(48);
      expect(store.ttlInput).assertEqual(48);
      const patch = fixture.transport.requests[1];
      expect(patch.method).assertEqual('PATCH');
      expect(patch.body).assertEqual('{"cache_ttl_hours":48}');
    });

    it('javdb_replace_sends_cas_payload_without_echoing_password', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 200, body: settingsBody(24) });
      const store = new SettingsStore();
      store.attach(fixture.client);
      store.load();
      await sleep(30);
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 200, body: settingsBody(24) });
      store.javdbUsername = 'newuser';
      store.javdbPassword = 'secret-pw';
      store.saveJavdb();
      await sleep(30);
      const patch = fixture.transport.requests[1];
      const raw = patch.body ?? '';
      expect(raw.includes('"action":"replace"')).assertTrue();
      expect(raw.includes('"expected_version":2')).assertTrue();
      expect(raw.includes('"password":"secret-pw"')).assertTrue();
      expect(store.javdbPassword).assertEqual('');
    });

    it('state_conflict_reloads_authoritative', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 200, body: settingsBody(24) });
      const store = new SettingsStore();
      store.attach(fixture.client);
      store.load();
      await sleep(30);
      fixture.transport.routes.set(`${BASE}/settings`, { statusCode: 422, body: '{"code":"state_conflict","message":"conflict","request_id":"r1"}' });
      store.setTtlInput(36);
      store.saveTtl();
      await sleep(30);
      expect(store.errorMessage).assertEqual('数据已变化，请刷新后重试');
      const gets = fixture.transport.requests.filter((r) => r.method === 'GET').length;
      expect(gets).assertEqual(2);
    });

    it('github_source_url_validation', 0, () => {
      expect(SettingsStore.isGithubSourceUrl('https://github.com/owner/repo')).assertTrue();
      expect(SettingsStore.isGithubSourceUrl('https://api.github.com/repos/owner/repo')).assertTrue();
      expect(SettingsStore.isGithubSourceUrl('http://github.com/owner/repo')).assertFalse();
      expect(SettingsStore.isGithubSourceUrl('https://github.com/owner/repo/extra')).assertFalse();
      expect(SettingsStore.isGithubSourceUrl('https://github.com/owner/repo?x=1')).assertFalse();
      expect(SettingsStore.isGithubSourceUrl('https://user@github.com/owner/repo')).assertFalse();
      expect(SettingsStore.isGithubSourceUrl('https://example.com/x')).assertFalse();
    });

    it('connection_test_maps_statuses', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/settings/connection-tests`, { statusCode: 200, body: '{"target":"javdb","status":"credentials_invalid","error_code":"javdb_credentials_invalid","elapsed_ms":120,"checked_at":"2026-08-06T00:00:00Z"}' });
      const store = new SettingsStore();
      store.attach(fixture.client);
      store.testConnection('javdb');
      await sleep(30);
      const test = store.connectionResults.get('javdb');
      expect(test !== undefined).assertTrue();
      if (test !== undefined) {
        expect(SettingsStore.connectionStatusText(test)).assertEqual('凭据无效');
        expect(SettingsStore.connectionErrorText(test)).assertEqual('JavDB 凭据无效');
      }
    });
  });

  describe('CacheStore', () => {
    it('loads_page_and_capacity', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/cache-jobs?limit=24`, { statusCode: 200, body: cachePageBody(cacheJobBody('10000000-0000-0000-0000-0000000000c1', 'queued'), 1, 2, 5) });
      const store = new CacheStore();
      store.attach(fixture.client, null);
      store.refresh();
      await sleep(30);
      expect(store.status).assertEqual(CachePageStatus.READY);
      expect(store.items.length).assertEqual(1);
      const cap1 = store.capacity;
      expect(cap1 !== null && cap1.runningLimit).assertEqual(2);
      const cap2 = store.capacity;
      expect(cap2 !== null && cap2.queuedLimit).assertEqual(10);
      const cap3 = store.capacity;
      expect(cap3 !== null && cap3.readyLimit).assertEqual(20);
    });

    it('cancel_sends_confirmed_and_replaces_item', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/cache-jobs?limit=24`, { statusCode: 200, body: cachePageBody(cacheJobBody('10000000-0000-0000-0000-0000000000c1', 'queued'), 1, 1, 0) });
      fixture.transport.routes.set(`${BASE}/cache-jobs/10000000-0000-0000-0000-0000000000c1/cancel`, { statusCode: 202, body: cacheJobBody('10000000-0000-0000-0000-0000000000c1', 'cancelling') });
      const store = new CacheStore();
      store.attach(fixture.client, null);
      store.refresh();
      await sleep(30);
      store.cancelJob('10000000-0000-0000-0000-0000000000c1');
      await sleep(30);
      expect(store.items.length).assertEqual(1);
      expect(store.items[0].status).assertEqual('cancelling');
      const cancel = fixture.transport.requests.find((r) => r.url.includes('/cancel'));
      expect(cancel !== undefined && cancel.body).assertEqual('{"confirmed":true}');
    });

    it('cancel_buttons_are_scoped', 0, () => {
      const queued = new CacheJobDetail('10000000-0000-0000-0000-0000000000c1', 'm', 's', 'queued', null, null, new Array<Object>(), new Array<string>(), new Array<Object>(), null, null, 't', 't');
      expect(CacheStore.canCancel(queued)).assertTrue();
      const ready = new CacheJobDetail('10000000-0000-0000-0000-0000000000c2', 'm', 's', 'ready', null, null, new Array<Object>(), new Array<string>(), new Array<Object>(), null, null, 't', 't');
      expect(CacheStore.canCancel(ready)).assertFalse();
      expect(CacheStore.canCleanup(ready)).assertTrue();
      const detached = new CacheJobDetail('10000000-0000-0000-0000-0000000000c3', 'm', 's', 'detached', null, null, new Array<Object>(), new Array<string>(), new Array<Object>(), null, null, 't', 't');
      expect(CacheStore.canCleanup(detached)).assertFalse();
      expect(CacheStore.statusText('awaiting_selection')).assertEqual('待选文件');
      expect(CacheStore.statusText('submit_uncertain')).assertEqual('提交待确认');
      expect(CacheStore.statusText('detached')).assertEqual('已失联');
    });

    it('active_lease_cleanup_keeps_item', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/cache-jobs?limit=24`, { statusCode: 200, body: cachePageBody(cacheJobBody('10000000-0000-0000-0000-0000000000c1', 'ready'), 0, 0, 1) });
      fixture.transport.routes.set(`${BASE}/cache-jobs/10000000-0000-0000-0000-0000000000c1/cleanup`, { statusCode: 409, body: '{"code":"cache_active_lease","message":"playing","request_id":"r1"}' });
      const store = new CacheStore();
      store.attach(fixture.client, null);
      store.refresh();
      await sleep(30);
      store.cleanupJob('10000000-0000-0000-0000-0000000000c1');
      await sleep(30);
      expect(store.items[0].status).assertEqual('ready');
      expect(store.errorMessage).assertEqual('缓存正在播放，暂时不能清理');
    });
  });

  describe('DiagnosticsStore', () => {
    it('loads_diagnostics_and_labels', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/admin/diagnostics`, { statusCode: 200, body: diagnosticsBody() });
      const store = new DiagnosticsStore();
      store.attach(fixture.client);
      store.load();
      await sleep(30);
      expect(store.status).assertEqual(DiagnosticsStatus.READY);
      const diagnostics = store.diagnostics;
      expect(diagnostics !== null).assertTrue();
      if (diagnostics !== null) {
        // queues.metadata_paused=false → store.paused 初始 false
        expect(store.paused).assertFalse();
        expect(diagnostics.components.length).assertEqual(2);
        expect(DiagnosticsStore.componentStatusText(diagnostics.components[0].status)).assertEqual('健康');
        expect(DiagnosticsStore.componentStatusText(diagnostics.components[1].status)).assertEqual('部分异常');
        expect(diagnostics.metadataProgress.total).assertEqual(10);
        expect(diagnostics.metadataProgress.currentNumbers[0]).assertEqual('ABC-123');
        expect(diagnostics.recentFailures.length).assertEqual(1);
        expect(diagnostics.connectionTests[0].status).assertEqual('available');
      }
    });

    it('paused_initializes_from_diagnostics', 0, async () => {
    const fixture = new StoreFixture();
    const pausedBody = diagnosticsBody().replace('"metadata_paused":false', '"metadata_paused":true');
    fixture.transport.routes.set(`${BASE}/admin/diagnostics`, { statusCode: 200, body: pausedBody });
    const store = new DiagnosticsStore();
    store.attach(fixture.client);
    store.load();
    await sleep(30);
    expect(store.paused).assertTrue();
  });

  it('toggles_pause_with_single_boolean', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/admin/metadata-queue`, { statusCode: 200, body: '{"paused":true,"queued":2,"running":1}' });
      const store = new DiagnosticsStore();
      store.attach(fixture.client);
      store.togglePause();
      await sleep(30);
      expect(store.paused).assertTrue();
      const put = fixture.transport.requests[0];
      expect(put.method).assertEqual('PUT');
      expect(put.body).assertEqual('{"paused":true}');
    });

    it('enrichment_stages_exclude_javdb_core', 0, () => {
      const stages = DiagnosticsStore.ENRICHMENT_STAGES;
      expect(stages.includes('javdb_core')).assertFalse();
      expect(stages.includes('translation')).assertTrue();
      expect(DiagnosticsStore.stageText('translation')).assertEqual('AI 翻译');
    });

    it('retry_enrichment_posts_selected_stages', 0, async () => {
      const fixture = new StoreFixture();
      fixture.transport.routes.set(`${BASE}/admin/metadata-jobs/10000000-0000-0000-0000-0000000000e1/retry-enrichment`,
        { statusCode: 201, body: '{"id":"10000000-0000-0000-0000-0000000000f1","number":"ABC-123","status":"queued","attempt_no":3,"requested_stages":["images","gfriends"],"retryable_stages":["images","gfriends"],"created_at":"2026-08-06T00:00:00Z"}' });
      const store = new DiagnosticsStore();
      store.attach(fixture.client);
      store.retryEnrichment('10000000-0000-0000-0000-0000000000e1', ['images', 'gfriends']);
      await sleep(30);
      expect(store.retryingJobId).assertNull();
      expect(store.retryFeedback !== null).assertTrue();
      const post = fixture.transport.requests[0];
      expect(post.body).assertEqual('{"stages":["images","gfriends"]}');
    });
  });
}
