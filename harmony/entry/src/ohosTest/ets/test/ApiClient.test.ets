/**
 * TASK-302 ApiClient/ServerProfile/认证契约测试。
 *
 * 使用内存 Fake 传输与 Fake 秘密存储；不访问真实网络/Asset Store。
 * 验证：401 单次 refresh、错误码映射、bootstrap header 单次携带、
 * 令牌写入 SecretStore 而非 Preferences、URL 策略边界。
 */

import { describe, it, expect } from '@ohos/hypium';
import { ApiClient, HttpRequest, HttpResponse, HttpTransport, SessionProvider } from '../../../main/ets/core/api/ApiClient';
import { ApiException, TokenPair } from '../../../main/ets/core/api/ApiModels';
import { ServerAddressCodes, ServerAddressException, ServerProfile } from '../../../main/ets/core/api/ServerProfile';
import { SecretStore, SecureSessionStore } from '../../../main/ets/core/auth/SecureSessionStore';

class FakeSecretStore implements SecretStore {
  private store: Map<string, string> = new Map();

  async write(alias: string, secret: string): Promise<void> {
    this.store.set(alias, secret);
  }

  async read(alias: string): Promise<string | null> {
    const value = this.store.get(alias);
    return value === undefined ? null : value;
  }

  async remove(alias: string): Promise<void> {
    this.store.delete(alias);
  }

  has(alias: string): boolean {
    return this.store.has(alias);
  }

  keys(): string[] {
    const result: string[] = [];
    this.store.forEach((_v, k) => result.push(k));
    return result;
  }
}

class QueuedResponse {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    this.status = status;
    this.body = body;
  }
}

class FakeHttpTransport implements HttpTransport {
  responses: QueuedResponse[] = [];
  requests: HttpRequest[] = [];

  async request(request: HttpRequest): Promise<HttpResponse> {
    this.requests.push(request);
    const next = this.responses.shift();
    if (next === undefined) {
      throw new ApiException('client_transport_error', 0, '', 'no queued response', null);
    }
    return { statusCode: next.status, body: next.body };
  }

  /** 构造 TokenPair JSON 响应。 */
  static tokenPairBody(access: string, refresh: string): string {
    return `{"access_token":"${access}","refresh_token":"${refresh}","token_type":"Bearer",` +
      `"access_expires_at":"2026-08-05T00:00:00Z","refresh_expires_at":"2026-09-03T00:00:00Z"}`;
  }

  /** 构造最小 EventSnapshot JSON。 */
  static snapshotBody(): string {
    return '{"snapshot_version":5,"last_event_id":"c1",' +
      '"queues":{"metadata_queued":0,"metadata_running":0,"metadata_paused":false,' +
      '"cache_queued":0,"cache_running":0,"cache_ready":0},' +
      '"cache_jobs":[],"metadata_jobs":[],' +
      '"cloud115_binding":{"status":"unbound"},"notifications":[]}';
  }
}

function makePair(access: string, refresh: string): TokenPair {
  return new TokenPair(access, refresh, 'Bearer', '2026-08-05T00:00:00Z', '2026-09-03T00:00:00Z');
}

export default function apiClientTest() {
  describe('ApiClientTest', () => {
    it('login_writes_refresh_to_secret_store', 0, async (done: Function) => {
      const fakeSecret = new FakeSecretStore();
      const session = new SecureSessionStore(fakeSecret);
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.tokenPairBody('acc1', 'ref1')));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);

      const pair = await client.login('admin', 'pw', 'client-1');
      expect(pair.accessToken).assertEqual('acc1');
      expect(session.getAccessToken()).assertEqual('acc1');
      expect(fakeSecret.has('sakuraplayer.refresh_token')).assertTrue();
      expect(fakeSecret.keys().length).assertEqual(1);
      done();
    });

    it('unauthorized_triggers_single_refresh_and_retry', 0, async (done: Function) => {
      const fakeSecret = new FakeSecretStore();
      const session = new SecureSessionStore(fakeSecret);
      await session.setTokens(makePair('old', 'ref1'));
      const transport = new FakeHttpTransport();
      // 第一次业务请求 401 → refresh 200 → 重发 200
      transport.responses.push(new QueuedResponse(401, '{"code":"authentication_required","message":"expired","request_id":"r1"}'));
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.tokenPairBody('new1', 'ref2')));
      transport.responses.push(new QueuedResponse(200, FakeHttpTransport.snapshotBody()));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);

      const snapshot = await client.getEventSnapshot();
      expect(snapshot.snapshotVersion).assertEqual(5);
      // refresh 端点只调用一次
      const refreshCalls = transport.requests.filter((r) => r.url.includes('/auth/refresh'));
      expect(refreshCalls.length).assertEqual(1);
      // 重发请求必须携带轮换后的新 token（P0 回归：旧 header 闭包会导致二次 401）
      const businessRequests = transport.requests.filter((r) => r.url.includes('/events/snapshot'));
      expect(businessRequests.length).assertEqual(2);
      expect(businessRequests[1].headers['Authorization']).assertEqual('Bearer new1');
      // 新 access token 已更新
      expect(session.getAccessToken()).assertEqual('new1');
      done();
    });

    it('refresh_failure_clears_tokens', 0, async (done: Function) => {
      const fakeSecret = new FakeSecretStore();
      const session = new SecureSessionStore(fakeSecret);
      await session.setTokens(makePair('old', 'ref1'));
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(401, '{"code":"authentication_required","message":"expired","request_id":"r1"}'));
      transport.responses.push(new QueuedResponse(401, '{"code":"refresh_token_invalid","message":"bad refresh","request_id":"r2"}'));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);

      let thrownCode = '';
      try {
        await client.getEventSnapshot();
      } catch (err) {
        thrownCode = (err as ApiException).code;
      }
      expect(thrownCode).assertEqual('refresh_token_invalid');
      expect(session.getAccessToken()).assertNull();
      expect(fakeSecret.has('sakuraplayer.refresh_token')).assertFalse();
      done();
    });

    it('bootstrap_token_used_once_in_header', 0, async (done: Function) => {
      const fakeSecret = new FakeSecretStore();
      const session = new SecureSessionStore(fakeSecret);
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(201, FakeHttpTransport.tokenPairBody('acc', 'ref')));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);

      await client.bootstrap('t'.repeat(43), 'admin', 'pw', 'client-1');
      const bootstrapRequest = transport.requests.find((r) => r.url.includes('/auth/bootstrap'));
      expect(bootstrapRequest != undefined).assertTrue();
      expect(bootstrapRequest!.headers['X-Bootstrap-Token']).assertEqual('t'.repeat(43));
      // bootstrap 请求不带 Authorization
      expect(bootstrapRequest!.headers['Authorization']).assertUndefined();
      done();
    });

    it('protocol_error_on_invalid_error_body', 0, async (done: Function) => {
      const fakeSecret = new FakeSecretStore();
      const session = new SecureSessionStore(fakeSecret);
      const transport = new FakeHttpTransport();
      transport.responses.push(new QueuedResponse(400, 'not-json'));
      const client = new ApiClient(transport, 'http://127.0.0.1:8000/api/v1', session);

      let thrownCode = '';
      try {
        await client.getEventSnapshot();
      } catch (err) {
        thrownCode = (err as ApiException).code;
      }
      expect(thrownCode).assertEqual('client_protocol_error');
      done();
    });
  });

  describe('ServerProfileTest', () => {
    it('accepts_https_any_host', 0, () => {
      const normalized = ServerProfile.normalize('https://nas.example.com:8443', false);
      expect(normalized).assertEqual('https://nas.example.com:8443');
    });

    it('rejects_public_http', 0, () => {
      let code = '';
      try {
        ServerProfile.normalize('http://example.com', false);
      } catch (err) {
        code = (err as ServerAddressException).code;
      }
      expect(code).assertEqual(ServerAddressCodes.PUBLIC_HTTP_FORBIDDEN);
    });

    it('private_http_requires_confirmation', 0, () => {
      let code = '';
      try {
        ServerProfile.normalize('http://192.168.1.10:8000', false);
      } catch (err) {
        code = (err as ServerAddressException).code;
      }
      expect(code).assertEqual(ServerAddressCodes.PRIVATE_HTTP_CONFIRMATION_REQUIRED);
      // 确认后允许
      const normalized = ServerProfile.normalize('http://192.168.1.10:8000', true);
      expect(normalized).assertEqual('http://192.168.1.10:8000');
    });

    it('rejects_userinfo_and_path', 0, () => {
      let userinfoCode = '';
      try {
        ServerProfile.normalize('https://user:pw@example.com', false);
      } catch (err) {
        userinfoCode = (err as ServerAddressException).code;
      }
      expect(userinfoCode).assertEqual(ServerAddressCodes.USERINFO_FORBIDDEN);

      let pathCode = '';
      try {
        ServerProfile.normalize('https://example.com/prefix', false);
      } catch (err) {
        pathCode = (err as ServerAddressException).code;
      }
      expect(pathCode).assertEqual(ServerAddressCodes.PATH_FORBIDDEN);
    });

    it('allows_loopback_http_without_confirmation', 0, () => {
      const normalized = ServerProfile.normalize('http://127.0.0.1:8000', false);
      expect(normalized).assertEqual('http://127.0.0.1:8000');
      const localhost = ServerProfile.normalize('http://localhost:8000', false);
      expect(localhost).assertEqual('http://localhost:8000');
    });

    it('rejects_unsupported_scheme_and_query', 0, () => {
      let schemeCode = '';
      try {
        ServerProfile.normalize('ftp://example.com', false);
      } catch (err) {
        schemeCode = (err as ServerAddressException).code;
      }
      expect(schemeCode).assertEqual(ServerAddressCodes.UNSUPPORTED_SCHEME);

      let queryCode = '';
      try {
        ServerProfile.normalize('https://example.com?x=1', false);
      } catch (err) {
        queryCode = (err as ServerAddressException).code;
      }
      expect(queryCode).assertEqual(ServerAddressCodes.QUERY_FORBIDDEN);
    });
  });
}
