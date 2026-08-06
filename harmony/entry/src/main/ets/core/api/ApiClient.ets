/**
 * SakuraPlayer 类型化 HTTP 客户端。
 *
 * - 所有业务请求携带 Bearer 访问令牌；401 只执行一次 refresh（single-flight）。
 * - 传输层通过 HttpTransport 抽象，测试注入 Fake；生产用 Network Kit http。
 * - 错误统一映射为 ApiException 稳定错误码；DTO 形状非法为 client_protocol_error。
 */

import { http } from '@kit.NetworkKit';
import {
  ActorDetail, ActorPage, ApiErrorBody, ApiException, BootstrapStatus, CacheJobDetail,
  CacheJobPage,
  Cloud115Binding, ConnectionTest, Diagnostics, EventSnapshot, JsonReader, MetadataJobPage,
  MetadataQueueControl,
  MetadataRetryResult, MovieDetail, MoviePage, PlaybackManifest, PlayRequestResult,
  ProtocolException, QrSession,
  RankingPage,
  SearchResult, Settings, TokenPair,
} from './ApiModels';

/** 与状态无关的 HTTP 传输层。 */
export interface HttpResponse {
  readonly statusCode: number;
  readonly body: string;
}

export interface HttpRequest {
  readonly method: string;
  readonly url: string;
  readonly headers: Record<string, string>;
  readonly body: string | null;
}

export interface HttpTransport {
  request(request: HttpRequest): Promise<HttpResponse>;
}

/** 会话存储抽象：由 SecureSessionStore 实现，避免 ApiClient 与其循环依赖。 */
export interface SessionProvider {
  getAccessToken(): string | null;
  getRefreshToken(): string | null;
  setTokens(pair: TokenPair): Promise<void>;
  clearTokens(): Promise<void>;
}

/** 认证请求选项。 */
export interface RequestOptions {
  auth: boolean;
  allowRefresh?: boolean;
  headers?: Record<string, string>;
  body?: string | null;
}

/** 登录/bootstrap 载荷。 */
interface CredentialsPayload {
  username: string;
  password: string;
  client_instance_id: string;
}

/** refresh 载荷。 */
interface RefreshPayload {
  refresh_token: string;
}

/** /movies 查询参数。 */
export interface MovieListParams {
  cursor?: string | null;
  limit?: number;
  categories?: string[];
  labels?: string[];
  sourceWebsite?: string | null;
  playable?: boolean | null;
  minResourceSizeMb?: number | null;
  maxResourceSizeMb?: number | null;
  sort?: string | null;
  favorite?: boolean;
}

/** /rankings 查询参数（board 必填；year 仅 top250 有效；省略 year=TOP250 总榜）。 */
export interface RankingQueryParams {
  board: string;
  year?: number | null;
  cursor?: string | null;
  limit?: number;
}

/** /actors 查询参数（q 去首尾空白后 1..200；空查询省略；favorite=true 收藏集合）。 */
export interface ActorListParams {
  query?: string | null;
  cursor?: string | null;
  limit?: number;
  favorite?: boolean;
}

/** 生产传输层：Network Kit http，请求结束后 finally destroy。 */
export class NetworkHttpTransport implements HttpTransport {
  private readonly connectTimeoutMs: number;
  private readonly readTimeoutMs: number;

  constructor(connectTimeoutMs: number = 10000, readTimeoutMs: number = 30000) {
    this.connectTimeoutMs = connectTimeoutMs;
    this.readTimeoutMs = readTimeoutMs;
  }

  async request(request: HttpRequest): Promise<HttpResponse> {
    const client = http.createHttp();
    try {
      const method = this.toRequestMethod(request.method);
      const response = await client.request(request.url, {
        method: method,
        header: request.headers,
        extraData: request.body ?? undefined,
        connectTimeout: this.connectTimeoutMs,
        readTimeout: this.readTimeoutMs,
        expectDataType: http.HttpDataType.STRING,
      });
      const code = response.responseCode;
      const body = typeof response.result === 'string' ? response.result : '';
      return { statusCode: code, body: body };
    } catch (err) {
      throw this.mapTransportError(err);
    } finally {
      client.destroy();
    }
  }

  private toRequestMethod(method: string): http.RequestMethod {
    switch (method) {
      case 'GET':
        return http.RequestMethod.GET;
      case 'POST':
        return http.RequestMethod.POST;
      case 'PUT':
        return http.RequestMethod.PUT;
      case 'DELETE':
        return http.RequestMethod.DELETE;
      default:
        throw new ApiException('client_protocol_error', 0, '', `unsupported method: ${method}`, null);
    }
  }

  private mapTransportError(err: Object): ApiException {
    const message = err instanceof Error ? err.message : String(err);
    const lowered = message.toLowerCase();
    if (lowered.includes('tls') || lowered.includes('certificate') || lowered.includes('ssl')) {
      return new ApiException('client_tls_error', 0, '', 'TLS 连接失败', null);
    }
    return new ApiException('client_transport_error', 0, '', '网络请求失败', null);
  }
}

/** 认证端点结果。 */
export interface AuthResult {
  readonly pair: TokenPair;
}

/**
 * 类型化 API 客户端。baseUrl 为绝对基址（含 /api/v1 前缀由调用方保证）。
 */
export class ApiClient {
  private readonly transport: HttpTransport;
  private readonly baseUrl: string;
  private readonly session: SessionProvider;
  private refreshInFlight: Promise<TokenPair> | null = null;

  constructor(transport: HttpTransport, baseUrl: string, session: SessionProvider) {
    this.transport = transport;
    this.baseUrl = baseUrl;
    this.session = session;
  }

  get base(): string {
    return this.baseUrl;
  }

  getAccessToken(): string | null {
    return this.session.getAccessToken();
  }

  // ---- 认证端点 ----

  /** GET /auth/bootstrap-status：唯一管理员是否已创建。 */
  async getBootstrapStatus(): Promise<BootstrapStatus> {
    const options: RequestOptions = { auth: false };
    const response = await this.request('/auth/bootstrap-status', 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return BootstrapStatus.fromReader(JsonReader.fromText(response.body));
  }

  /** POST /auth/bootstrap：X-Bootstrap-Token 单次携带，成功后写入令牌。 */
  async bootstrap(token: string, username: string, password: string, clientInstanceId: string): Promise<TokenPair> {
    const payload: CredentialsPayload = {
      username: username, password: password, client_instance_id: clientInstanceId,
    };
    const body = JSON.stringify(payload);
    const headers: Record<string, string> = { 'X-Bootstrap-Token': token };
    const options: RequestOptions = { auth: false, headers: headers, body: body };
    const response = await this.request('/auth/bootstrap', 'POST', options);
    if (response.statusCode !== 201) {
      throw this.throwForError(response);
    }
    const pair = TokenPair.fromReader(JsonReader.fromText(response.body));
    await this.session.setTokens(pair);
    return pair;
  }

  /** POST /auth/login：登录并写令牌。 */
  async login(username: string, password: string, clientInstanceId: string): Promise<TokenPair> {
    const payload: CredentialsPayload = {
      username: username, password: password, client_instance_id: clientInstanceId,
    };
    const body = JSON.stringify(payload);
    const options: RequestOptions = { auth: false, body: body };
    const response = await this.request('/auth/login', 'POST', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    const pair = TokenPair.fromReader(JsonReader.fromText(response.body));
    await this.session.setTokens(pair);
    return pair;
  }

  /** POST /auth/refresh：轮换令牌；single-flight，并发 401 只刷新一次。 */
  async refresh(): Promise<TokenPair> {
    if (this.refreshInFlight !== null) {
      return this.refreshInFlight;
    }
    const inFlight = this.performRefresh();
    this.refreshInFlight = inFlight;
    try {
      return await inFlight;
    } finally {
      if (this.refreshInFlight === inFlight) {
        this.refreshInFlight = null;
      }
    }
  }

  private async performRefresh(): Promise<TokenPair> {
    const refreshToken = this.session.getRefreshToken();
    if (refreshToken === null) {
      await this.session.clearTokens();
      throw new ApiException('refresh_token_invalid', 401, '', '缺少刷新令牌，请重新登录', null);
    }
    const payload: RefreshPayload = { refresh_token: refreshToken };
    const request: HttpRequest = {
      method: 'POST',
      url: `${this.baseUrl}/auth/refresh`,
      headers: this.jsonHeaders(),
      body: JSON.stringify(payload),
    };
    let response: HttpResponse;
    try {
      response = await this.transport.request(request);
    } catch (err) {
      await this.session.clearTokens();
      throw err as Error;
    }
    if (response.statusCode !== 200) {
      await this.session.clearTokens();
      throw this.throwForError(response);
    }
    let pair: TokenPair;
    try {
      pair = TokenPair.fromReader(JsonReader.fromText(response.body));
    } catch (err) {
      await this.session.clearTokens();
      throw err as Error;
    }
    await this.session.setTokens(pair);
    return pair;
  }

  /** POST /auth/logout：撤销当前 refresh 会话；调用方负责清本地令牌与字幕缓存。 */
  async logout(): Promise<void> {
    const options: RequestOptions = { auth: true, allowRefresh: false };
    const response = await this.request('/auth/logout', 'POST', options);
    if (response.statusCode !== 204 && response.statusCode !== 401) {
      throw this.throwForError(response);
    }
  }

  // ---- 事件端点 ----

  /** GET /events/snapshot：REST 恢复快照。 */
  async getEventSnapshot(): Promise<EventSnapshot> {
    const options: RequestOptions = { auth: true };
    const response = await this.request('/events/snapshot', 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return EventSnapshot.fromText(response.body);
  }

  // ---- 发现端点 ----

  /** GET /search：全局搜索（番号/标题/别名，影片与女优分组）。 */
  async search(query: string, limit: number): Promise<SearchResult> {
    const encoded = encodeURIComponent(query);
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/search?q=${encoded}&limit=${limit}`, 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return SearchResult.fromText(response.body);
  }

  // ---- 目录端点 ----

  /** GET /movies：去重影片分页列表（游标绑定筛选/排序/收藏）。 */
  async listMovies(params: MovieListParams): Promise<MoviePage> {
    const query = this.buildMovieQuery(params);
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/movies${query}`, 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return MoviePage.fromText(response.body);
  }

  /** GET /rankings：只读本地榜单快照（board + top250 可选 year + 游标分页）。 */
  async getRanking(params: RankingQueryParams): Promise<RankingPage> {
    const query = this.buildRankingQuery(params);
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/rankings${query}`, 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return RankingPage.fromText(response.body);
  }

  // ---- 女优端点 ----

  /** GET /actors：姓名/别名搜索或收藏集合分页列表。 */
  async listActors(params: ActorListParams): Promise<ActorPage> {
    const query = this.buildActorQuery(params);
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/actors${query}`, 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return ActorPage.fromText(response.body);
  }

  /** GET /actors/{id}：女优详情（头像/简介/写真/关联影片）。 */
  async getActor(actorId: string): Promise<ActorDetail> {
    const encoded = encodeURIComponent(actorId);
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/actors/${encoded}`, 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return ActorDetail.fromText(response.body);
  }

  /** PUT/DELETE /actors/{id}/favorite：幂等收藏切换（204）。 */
  async setActorFavorite(actorId: string, enabled: boolean): Promise<void> {
    const encoded = encodeURIComponent(actorId);
    const method = enabled ? 'PUT' : 'DELETE';
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/actors/${encoded}/favorite`, method, options);
    if (response.statusCode !== 204) {
      throw this.throwForError(response);
    }
  }

  private buildMovieQuery(params: MovieListParams): string {
    const parts: string[] = [];
    if (params.cursor !== null && params.cursor !== undefined && params.cursor.length > 0) {
      parts.push(`cursor=${encodeURIComponent(params.cursor)}`);
    }
    if (params.limit !== undefined) {
      parts.push(`limit=${params.limit}`);
    }
    if (params.categories !== undefined && params.categories.length > 0) {
      parts.push(`categories=${encodeURIComponent(params.categories.join(','))}`);
    }
    if (params.labels !== undefined && params.labels.length > 0) {
      parts.push(`labels=${encodeURIComponent(params.labels.join(','))}`);
    }
    if (params.sourceWebsite !== null && params.sourceWebsite !== undefined && params.sourceWebsite.length > 0) {
      parts.push(`source_website=${encodeURIComponent(params.sourceWebsite)}`);
    }
    if (params.playable !== null && params.playable !== undefined) {
      parts.push(`playable=${params.playable}`);
    }
    if (params.minResourceSizeMb !== null && params.minResourceSizeMb !== undefined) {
      parts.push(`min_resource_size_mb=${params.minResourceSizeMb}`);
    }
    if (params.maxResourceSizeMb !== null && params.maxResourceSizeMb !== undefined) {
      parts.push(`max_resource_size_mb=${params.maxResourceSizeMb}`);
    }
    if (params.sort !== null && params.sort !== undefined && params.sort.length > 0) {
      parts.push(`sort=${encodeURIComponent(params.sort)}`);
    }
    if (params.favorite === true) {
      parts.push('favorite=true');
    }
    return parts.length > 0 ? `?${parts.join('&')}` : '';
  }

  private buildRankingQuery(params: RankingQueryParams): string {
    const parts: string[] = [];
    parts.push(`board=${encodeURIComponent(params.board)}`);
    if (params.year !== null && params.year !== undefined) {
      parts.push(`year=${params.year}`);
    }
    if (params.cursor !== null && params.cursor !== undefined && params.cursor.length > 0) {
      parts.push(`cursor=${encodeURIComponent(params.cursor)}`);
    }
    if (params.limit !== undefined) {
      parts.push(`limit=${params.limit}`);
    }
    return `?${parts.join('&')}`;
  }

  private buildActorQuery(params: ActorListParams): string {
    const parts: string[] = [];
    const query = params.query !== null && params.query !== undefined ? params.query.trim() : '';
    if (query.length > 0) {
      parts.push(`q=${encodeURIComponent(query)}`);
    }
    if (params.cursor !== null && params.cursor !== undefined && params.cursor.length > 0) {
      parts.push(`cursor=${encodeURIComponent(params.cursor)}`);
    }
    if (params.limit !== undefined) {
      parts.push(`limit=${params.limit}`);
    }
    if (params.favorite === true) {
      parts.push('favorite=true');
    }
    return parts.length > 0 ? `?${parts.join('&')}` : '';
  }

  /** PUT /notifications/{id}/read：幂等标记已读。 */
  async markNotificationRead(notificationId: string): Promise<void> {
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/notifications/${notificationId}/read`, 'PUT', options);
    if (response.statusCode !== 200 && response.statusCode !== 404) {
      throw this.throwForError(response);
    }
  }

  // ---- 内部请求 ----

  private jsonHeaders(): Record<string, string> {
    return { 'Content-Type': 'application/json', 'Accept': 'application/json' };
  }

  private authHeaders(): Record<string, string> {
    const token = this.session.getAccessToken();
    const headers = this.jsonHeaders();
    if (token !== null) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  private async request(path: string, method: string, options: RequestOptions):
    Promise<HttpResponse> {
    // 每次发送动态构建 headers：401 refresh 轮换 token 后重发必须携带新 Bearer
    const attempt = async (): Promise<HttpResponse> => {
      const requestHeaders = options.auth ? this.authHeaders() : this.jsonHeaders();
      if (options.headers !== undefined) {
        for (const key of Object.keys(options.headers)) {
          requestHeaders[key] = options.headers[key];
        }
      }
      const request: HttpRequest = {
        method: method,
        url: `${this.baseUrl}${path}`,
        headers: requestHeaders,
        body: options.body ?? null,
      };
      return this.transport.request(request);
    };

    let response = await attempt();
    if (options.auth && response.statusCode === 401 && (options.allowRefresh ?? true)) {
      const tokenAtSend = this.session.getAccessToken();
      try {
        await this.refresh();
      } catch (err) {
        throw err as Error;
      }
      if (this.session.getAccessToken() !== tokenAtSend) {
        // 令牌已更新：重发一次
        response = await attempt();
      }
    }
    return response;
  }

  /** 解析错误响应为稳定错误码 ApiException。 */
  private throwForError(response: HttpResponse): ApiException {
    let error: ApiErrorBody | null = null;
    try {
      const reader = JsonReader.fromText(response.body);
      error = ApiErrorBody.fromReader(reader);
    } catch (err) {
      // 响应不是合法 ApiError：协议错误
    }
    if (error !== null) {
      return new ApiException(error.code, response.statusCode, error.requestId, error.message, error.details);
    }
    return new ApiException('client_protocol_error', response.statusCode, '', '服务端响应格式非法', null);
  }

  /** GET /movies/{id}：聚合影片详情（无磁力/上游播放 URL）。 */
  async getMovie(movieId: string): Promise<MovieDetail> {
    const encoded = encodeURIComponent(movieId);
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/movies/${encoded}`, 'GET', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return MovieDetail.fromText(response.body);
  }

  /** PUT/DELETE /movies/{id}/favorite：幂等影片收藏切换（204）。 */
  async setMovieFavorite(movieId: string, enabled: boolean): Promise<void> {
    const encoded = encodeURIComponent(movieId);
    const method = enabled ? 'PUT' : 'DELETE';
    const options: RequestOptions = { auth: true };
    const response = await this.request(`/movies/${encoded}/favorite`, method, options);
    if (response.statusCode !== 204) {
      throw this.throwForError(response);
    }
  }
  /** GET /cloud115/binding：脱敏绑定状态。 */
  async getCloud115Binding(): Promise<Cloud115Binding> {
    const response = await this.request('/cloud115/binding', 'GET', { auth: true });
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return Cloud115Binding.fromReader(JsonReader.fromText(response.body));
  }

  /** DELETE /cloud115/binding：解绑（活动缓存任务 409）。 */
  async deleteCloud115Binding(): Promise<void> {
    const response = await this.request('/cloud115/binding', 'DELETE', { auth: true });
    if (response.statusCode !== 204) {
      throw this.throwForError(response);
    }
  }

  /** POST /cloud115/qr-sessions：创建扫码会话（201）。 */
  async createCloud115QrSession(): Promise<QrSession> {
    const response = await this.request('/cloud115/qr-sessions', 'POST', { auth: true });
    if (response.statusCode !== 201) {
      throw this.throwForError(response);
    }
    return QrSession.fromText(response.body);
  }

  /** GET /cloud115/qr-sessions/{id}：轮询扫码状态。 */
  async getCloud115QrSession(qrSessionId: string): Promise<QrSession> {
    const encoded = encodeURIComponent(qrSessionId);
    const response = await this.request(`/cloud115/qr-sessions/${encoded}`, 'GET', { auth: true });
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return QrSession.fromText(response.body);
  }

  /** POST /cloud115/qr-sessions/{id}/confirm：确认扫码并保存绑定。 */
  async confirmCloud115QrSession(qrSessionId: string): Promise<Cloud115Binding> {
    const encoded = encodeURIComponent(qrSessionId);
    const response = await this.request(`/cloud115/qr-sessions/${encoded}/confirm`, 'POST', { auth: true });
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return Cloud115Binding.fromReader(JsonReader.fromText(response.body));
  }

  /** POST /cache-jobs/{id}/playback-sessions：创建 12 小时播放会话（AC-099/101/102）。 */
  async createPlaybackSession(cacheJobId: string, mediaId: string, mode: string,
    clientInstanceId: string): Promise<PlaybackManifest> {
    const encoded = encodeURIComponent(cacheJobId);
    const options: RequestOptions = {
      auth: true,
      body: JSON.stringify({
        'media_id': mediaId,
        'mode': mode,
        'platform': 'harmonyos',
        'client_instance_id': clientInstanceId,
      }),
    };
    const response = await this.request(`/cache-jobs/${encoded}/playback-sessions`, 'POST', options);
    if (response.statusCode !== 201) {
      throw this.throwForError(response);
    }
    return PlaybackManifest.fromText(response.body);
  }

  /** POST /movies/{id}/play-requests：唯一创建离线任务的入口（Idempotency-Key 幂等）。 */
  async createPlayRequest(movieId: string, sourceId: string, idempotencyKey: string): Promise<PlayRequestResult> {
    if (!/^[A-Za-z0-9._~-]{16,128}$/.test(idempotencyKey)) {
      throw new ProtocolException('idempotency key must be safe ascii 16..128');
    }
    const encoded = encodeURIComponent(movieId);
    const options: RequestOptions = {
      auth: true,
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ 'source_id': sourceId }),
    };
    const response = await this.request(`/movies/${encoded}/play-requests`, 'POST', options);
    if (response.statusCode !== 200 && response.statusCode !== 202) {
      throw this.throwForError(response);
    }
    return PlayRequestResult.fromText(response.body);
  }

  /** GET /cache-jobs：分页任务列表 + 容量。 */
  async listCacheJobs(statuses: string[], cursor: string | null): Promise<CacheJobPage> {
    const parts: string[] = [];
    if (statuses.length > 0) {
      parts.push(`status=${encodeURIComponent(statuses.join(','))}`);
    }
    parts.push('limit=24');
    if (cursor !== null) {
      parts.push(`cursor=${encodeURIComponent(cursor)}`);
    }
    const response = await this.request(`/cache-jobs?${parts.join('&')}`, 'GET', { auth: true });
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return CacheJobPage.fromText(response.body);
  }

  /** POST /cache-jobs/{id}/cancel：取消（二次确认 {confirmed:true}，202 返回新任务）。 */
  async cancelCacheJob(cacheJobId: string): Promise<CacheJobDetail> {
    const encoded = encodeURIComponent(cacheJobId);
    const options: RequestOptions = { auth: true, body: '{"confirmed":true}' };
    const response = await this.request(`/cache-jobs/${encoded}/cancel`, 'POST', options);
    if (response.statusCode !== 202) {
      throw this.throwForError(response);
    }
    return CacheJobDetail.fromText(response.body);
  }

  /** POST /cache-jobs/{id}/cleanup：清理就绪缓存（202 返回新任务）。 */
  async cleanupCacheJob(cacheJobId: string): Promise<CacheJobDetail> {
    const encoded = encodeURIComponent(cacheJobId);
    const options: RequestOptions = { auth: true, body: '' };
    const response = await this.request(`/cache-jobs/${encoded}/cleanup`, 'POST', options);
    if (response.statusCode !== 202) {
      throw this.throwForError(response);
    }
    return CacheJobDetail.fromText(response.body);
  }

  /** GET /admin/diagnostics：脱敏诊断（组件/队列/失败/连接测试）。 */
  async getDiagnostics(): Promise<Diagnostics> {
    const response = await this.request('/admin/diagnostics', 'GET', { auth: true });
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return Diagnostics.fromText(response.body);
  }

  /** GET /settings：权威设置（非秘密现值回显）。 */
  async getSettings(): Promise<Settings> {
    const response = await this.request('/settings', 'GET', { auth: true });
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return Settings.fromText(response.body);
  }

  /** PATCH /settings：对象级更新（TTL/CAS replace/clear），body 为 JSON 串，响应为权威真相。 */
  async updateSettings(body: string): Promise<Settings> {
    const options: RequestOptions = { auth: true, body: body };
    const response = await this.request('/settings', 'PATCH', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return Settings.fromText(response.body);
  }

  /** POST /settings/connection-tests：单一目标只读 probe。 */
  async testConnection(target: string): Promise<ConnectionTest> {
    const options: RequestOptions = { auth: true, body: JSON.stringify({ 'target': target }) };
    const response = await this.request('/settings/connection-tests', 'POST', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return ConnectionTest.fromText(response.body);
  }

  /** POST /settings/mgdb-sync-requests：立即全量同步（202 创建/复用）。 */
  async requestMgdbFullSync(): Promise<void> {
    const options: RequestOptions = { auth: true, body: '' };
    const response = await this.request('/settings/mgdb-sync-requests', 'POST', options);
    if (response.statusCode !== 202) {
      throw this.throwForError(response);
    }
  }

  /** PUT /admin/metadata-queue：暂停/恢复元数据领取（单一布尔）。 */
  async setMetadataQueueControl(paused: boolean): Promise<MetadataQueueControl> {
    const options: RequestOptions = { auth: true, body: JSON.stringify({ 'paused': paused }) };
    const response = await this.request('/admin/metadata-queue', 'PUT', options);
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return MetadataQueueControl.fromText(response.body);
  }

  /** GET /admin/metadata-jobs：持久元数据队列（可筛选状态）。 */
  async listMetadataJobs(status: string | null, cursor: string | null): Promise<MetadataJobPage> {
    const parts: string[] = [];
    if (status !== null) {
      parts.push(`status=${encodeURIComponent(status)}`);
    }
    parts.push('limit=24');
    if (cursor !== null) {
      parts.push(`cursor=${encodeURIComponent(cursor)}`);
    }
    const response = await this.request(`/admin/metadata-jobs?${parts.join('&')}`, 'GET', { auth: true });
    if (response.statusCode !== 200) {
      throw this.throwForError(response);
    }
    return MetadataJobPage.fromText(response.body);
  }

  /** POST /admin/metadata-jobs/{id}/retry：失败元数据任务重试（201 新 queued attempt）。 */
  async retryMetadataJob(metadataJobId: string): Promise<MetadataRetryResult> {
    const encoded = encodeURIComponent(metadataJobId);
    const response = await this.request(`/admin/metadata-jobs/${encoded}/retry`, 'POST', { auth: true });
    if (response.statusCode !== 201) {
      throw this.throwForError(response);
    }
    return MetadataRetryResult.fromText(response.body);
  }

  /** POST /admin/metadata-jobs/{id}/retry-enrichment：显式阶段富化重试（永不跑 javdb_core）。 */
  async retryMetadataEnrichment(metadataJobId: string, stages: string[]): Promise<MetadataRetryResult> {
    const encoded = encodeURIComponent(metadataJobId);
    const options: RequestOptions = { auth: true, body: JSON.stringify({ 'stages': stages }) };
    const response = await this.request(`/admin/metadata-jobs/${encoded}/retry-enrichment`, 'POST', options);
    if (response.statusCode !== 201) {
      throw this.throwForError(response);
    }
    return MetadataRetryResult.fromText(response.body);
  }
}


export class ClientErrorCodes {
  static readonly PROTOCOL = 'client_protocol_error';
  static readonly TRANSPORT = 'client_transport_error';
  static readonly TLS = 'client_tls_error';
  static readonly REFRESH_INVALID = 'refresh_token_invalid';
}
