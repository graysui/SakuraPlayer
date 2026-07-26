# SakuraPlayer 项目架构

**创建日期**: 2026-07-24

**最后更新**: 2026-07-24

**状态**: Frozen for v1

**适用范围**: Docker 后端、Windows 客户端、HarmonyOS 客户端

## 1. 逻辑架构

SakuraPlayer 是单管理员、单 115 账号的私有部署产品。后端采用模块化单体和独立工作进程，客户端只访问后端发布的 REST、WebSocket 与短期播放入口。视频字节由客户端在后端 `302` 后直接向 115/CDN 获取。

### 1.1 限界上下文

| 限界上下文 | 职责 | 拥有的数据 | 上游依赖 |
|---|---|---|---|
| 身份与配置 | 唯一管理员、访问令牌、115/JavDB/AI 配置、密钥保护 | 管理员、刷新会话、加密配置 | 无 |
| 资源接入 | AVdb Release 发现、校验、解密、幂等导入、拒绝标记、待识别资源 | 同步批次、原始资源、来源拒绝标记 | 身份与配置 |
| 目录与元数据 | 影片、女优、标签、图片、元数据任务、翻译、演员映射 | 目录聚合、刮削任务、翻译记录、永久图片清单 | 资源接入、身份与配置 |
| 发现 | 媒体库查询、搜索、排行榜快照、收藏 | 榜单快照、影片/女优收藏 | 目录与元数据、资源接入、115 播放缓存、播放 |
| 115 播放缓存 | 单账户绑定、离线队列、任务目录、文件解析、TTL/LRU、安全清理 | 115 绑定、缓存任务、远端文件定位、清理记录 | 资源接入、身份与配置 |
| 播放 | 短期播放会话、原画/HLS 派发、字幕、租约、影片级进度 | 播放会话、租约、进度、本地字幕副本状态 | 115 播放缓存、目录与元数据 |
| 客户端体验 | Windows 与 HarmonyOS 页面、路由、通知、本地安全存储 | 本机令牌、页面状态、临时图片与字幕缓存 | 所有后端公开契约 |

### 1.2 模块关系

```text
Windows Flutter                         HarmonyOS ArkTS
       |                                      |
       +----------- REST / WebSocket ---------+
                              |
                       FastAPI API 进程
                              |
       +-------------+--------+---------+-------------+
       |             |                  |             |
   Identity       Catalog           Cache API      Playback
       |             |                  |             |
       +-------- PostgreSQL 事务与持久事件 -----------+
                     |                  |
              Scheduler 进程       Worker 进程
                     |                  |
             AVdb/JavDB/DMM/AI      115 Adapter
                                        |
                                115 / 115 CDN
```

业务依赖只允许沿表中方向流动。`catalog` 不得直接调用客户端或 115 SDK；`playback_cache` 不得把磁力、Cookie 或 115 短期 URL发布为公共领域对象。

### 1.3 共享内核

| 共享概念 | 使用者 | 约束 |
|---|---|---|
| `MovieId` / `MovieNumber` | 资源、目录、发现、缓存、播放 | 影片以规范化番号聚合，内部 ID 不对外推断 |
| `ActorId` | 目录、发现、客户端 | 姓名不是身份主键 |
| `SourceId` | 资源、缓存、详情页 | 指向一条 AVdb 来源帖子，不接受客户端提交任意磁力 |
| `TaskId` / `EventId` | 元数据、缓存、WebSocket | UUID；事件可按 ID 去重 |
| `ErrorCode` | 后端与两端客户端 | 稳定英文小写蛇形码，文案由客户端本地化 |
| `PageCursor` | 目录、发现、诊断 | 不暴露数据库偏移实现 |
| `PlatformUserAgent` | 播放、Windows、HarmonyOS | 每个平台固定且参与播放签名验证 |
| `BootstrapToken` | 身份、部署 | 只在无管理员时验证，不持久化 |
| `ApiBaseUrl` | Windows、HarmonyOS | 本机非敏感设置，更换时清空当前会话 |

### 1.4 上下文映射

| 上游 | 下游 | 关系 | 契约 |
|---|---|---|---|
| 资源接入 | 目录与元数据 | 发布语言 | `SourceImported` 与规范化番号 |
| 目录与元数据 | 发现 | 发布语言 | 只读目录查询与 `core_ready` 可见性 |
| 115 播放缓存 | 发现 | 发布语言 | `SourceAvailabilityPort` 批量只读来源状态 |
| 播放 | 发现 | 发布语言 | `PlaybackStatePort` 批量只读影片进度 |
| 资源接入 | 115 播放缓存 | 客户-供应商 | 只传 `SourceId` 和服务端解密后的提交载荷 |
| 115 播放缓存 | 播放 | 发布语言 | 只传就绪远端媒体定位，不传磁力 |
| 身份与配置 | 外部适配器 | 防腐层 | 适配器拿到解密后的短生命周期凭据对象 |
| 后端 | 客户端体验 | 开放主机服务 | OpenAPI 3.1、版本化 WebSocket 事件、错误码目录 |
| 115/JavDB/DMM/AI | 后端 | 防腐层 | 外部响应先映射为内部 DTO，禁止向领域层透传任意 JSON |

## 2. 基础设施架构

### 2.1 部署拓扑

```text
家庭局域网 / VPN
  |
  +-- Windows 客户端
  +-- HarmonyOS 客户端
  |
  +-- HTTPS / trusted VPN --> api:8000
                              |
               +--------------+--------------+
               |                             |
          postgres:5432                  持久化卷
               ^                       images/manifests/logs
               |
       +-------+--------+
       |                |
   scheduler          worker
       |                |
   定时入队/清理      元数据/115 状态机
       |                |
       +------ 外部 HTTPS API ------+
                                    |
                    GitHub / JavDB / DMM / GFriends / AI / 115

播放器 -- GET 签名入口 --> api -- 302 --> 115/CDN
播放器 ================= 视频字节直连 =================> 115/CDN
```

### 2.2 组件基线

| 组件 | 技术 | 固定版本 | 目的 |
|---|---|---:|---|
| 容器运行时 | Docker Engine | 28.2.2 | 后端打包与运行 |
| 编排 | Docker Compose | 2.37.1 | 私有单机部署 |
| API | FastAPI + Uvicorn | 0.110.1 + 0.22.0 | REST、WebSocket、播放重定向 |
| Worker | Python 独立进程 | 3.10.16 | 元数据与 115 持久任务 |
| Scheduler | APScheduler | 3.10.4 | 仅负责确定性定时入队和维护任务 |
| 数据库 | PostgreSQL | 17.5 | 业务数据、任务队列、互斥、事件日志 |
| 文件卷 | Docker named volumes | Compose 2.37.1 | 永久图片、上游清单缓存、必要日志 |
| Windows | Flutter | 3.29.2 | Windows 10/11 桌面客户端 |
| HarmonyOS | HarmonyOS SDK | 6.1.1 Release / API 24 | ArkTS/ArkUI 原生手机端 |

版本是 v1 实现基线。升级必须单独提交依赖验证记录，不得在功能任务中顺带升级。

### 2.3 网络边界

| 区域 | 可访问方 | 规则 |
|---|---|---|
| 客户端入口 | 家庭 LAN 或 VPN 客户端 | 默认只发布 loopback；远程使用 HTTPS 或可信加密 VPN，不提供公网部署向导 |
| 应用网络 | `api`、`worker`、`scheduler` | 可访问 PostgreSQL 和所需外部 HTTPS 站点 |
| 数据网络 | 仅后端容器 | PostgreSQL 不映射到宿主公网 |
| 115/CDN | 两端播放器 | 仅通过后端签名入口产生的 `302` 到达 |
| 管理端点 | 已认证管理员 | 无匿名设置、诊断、任务或签发入口 |

### 2.4 并发和扩展边界

v1 是单机单管理员产品，不做水平自动扩展。所有上限由数据库事务和 worker 领取逻辑保证，而不是依赖单进程内计数。

| 工作负载 | 固定边界 | 协调方式 |
|---|---:|---|
| 元数据影片任务 | 3 个运行中 | PostgreSQL `FOR UPDATE SKIP LOCKED` + 父进程子进程槽位 |
| 单元数据任务 | 600 秒 | 父进程终止完整子进程组，持久化失败 |
| 排行榜同步 | 同榜单/年份 1 个活动请求 | PostgreSQL 部分唯一索引 + worker claim token/lease |
| 115 离线 | 2 个运行中 | 数据库部分唯一约束与槽位事务 |
| 115 排队 | 10 个 | 创建任务事务内计数，超限拒绝 |
| 就绪缓存 | 默认 20 个 | LRU 选择器；活跃租约排除 |
| WebSocket | 单管理员多客户端 | 持久事件游标 + REST 快照恢复 |

### 2.5 持久化卷

| 卷 | 保留内容 | 不允许内容 |
|---|---|---|
| `db-data` | PostgreSQL 数据 | 无 |
| `catalog-images` | 封面、剧照、永久演员图片 | GFriends 全量镜像、视频、字幕 |
| `provider-cache` | AVdb 加密包摘要、演员映射、GFriends 索引、最近成功清单 | Cookie、AI 明文密钥 |
| `app-logs` | 脱敏结构化日志 | 完整磁力、Cookie、签名 URL、令牌 |

客户端字幕只进入应用私有缓存，不进入后端卷。客户端卸载、退出登录、对应 115 缓存清理或本地过期时删除。

### 2.6 环境

| 环境 | 用途 | 外部访问策略 |
|---|---|---|
| `test` | 自动单元和集成测试 | 默认禁止真实 115、JavDB 写操作和付费 AI |
| `development` | 本地 Docker 与客户端调试 | 可用固定样本或显式开发凭据 |
| `production-private` | loopback、家庭私网或 VPN | 真实外部依赖；秘密从 Docker Secret/环境变量注入；远程访问使用 HTTPS/VPN |
| `acceptance-real115` | 发布门禁 | 显式标记运行，使用专用测试目录和人工确认 |

## 3. 软件架构

### 3.1 技术栈

| 层 | 技术 | 固定版本 | 说明 |
|---|---|---:|---|
| 后端语言 | Python | 3.10.16 | 与参考项目可移植代码保持兼容 |
| Web | FastAPI / Starlette | 0.110.1 / 0.37.2 | Async REST 与 WebSocket |
| Schema | Pydantic / pydantic-settings | 2.7.4 / 2.2.1 | 边界校验与设置 |
| ORM | SQLAlchemy | 2.0.41 | 显式事务、行锁、PostgreSQL 特性 |
| 迁移 | Alembic | 1.16.2 | 单向版本迁移和启动 Schema 门禁 |
| PostgreSQL 驱动 | psycopg | 3.2.9 | 同步 worker 与 async API 双实现 |
| HTTP | httpx | 0.28.1 | 所有外部适配器，统一超时和脱敏日志 |
| XML 安全解析 | defusedxml | 0.7.1 | Actor Mapping 禁用 DTD、实体和外部网络 |
| 图片验证 | Pillow | 11.2.1 | 永久图片完整解码、真实格式和像素边界 |
| 加密 | cryptography | 45.0.4 | AVdb AES-GCM 与配置 AES-GCM |
| 密码 | argon2-cffi | 23.1.0 | Argon2id 管理员密码哈希 |
| 令牌 | PyJWT | 2.10.1 | 访问/刷新令牌签发与验证 |
| 调度 | APScheduler | 3.10.4 | 固定 cron 入队，不承担业务真相 |
| 后端测试 | pytest / pytest-asyncio | 8.4.1 / 1.0.0 | 单元、数据库集成、替身 E2E |
| Windows UI | Flutter / Dart | 3.29.2 / 3.7.2 | 仅 Windows 构建 |
| Windows 状态 | flutter_riverpod | 3.1.0 | 单一状态方案 |
| Windows 路由 | go_router | 16.3.0 | typed route 与桌面 Shell |
| Windows HTTP | dio | 5.7.0 | REST、字节下载、WebSocket 握手配置 |
| Windows 播放 | media_kit / media_kit_video / media_kit_libs_video | 1.1.11 / 1.2.5 / 1.0.5 | libmpv、libass、Range/HLS |
| Windows 安全存储 | flutter_secure_storage | 9.2.0 | 刷新令牌与客户端实例 ID |
| HarmonyOS | ArkTS / ArkUI / AVPlayer | API 24 | 无跨平台 UI 运行时 |

### 3.2 数据架构

| 组件 | 选择 | 约束 |
|---|---|---|
| 主数据库 | PostgreSQL 17.5 | 唯一业务真相；不支持生产 SQLite |
| 队列 | PostgreSQL 表队列 | 不引入 Redis、RabbitMQ、Celery |
| 事件 | PostgreSQL 持久事件表 | WebSocket 是投递通道，不是状态真相 |
| 搜索 | PostgreSQL B-tree + `pg_trgm` | 精确番号优先，标题/别名模糊查询 |
| 文件 | 本地持久卷 | 原子临时文件替换，数据库保存相对路径和摘要 |
| 短期 URL | 仅进程内 | 115 原画/HLS URL、字幕下载 URL不得落库 |

### 3.3 架构风格

后端采用模块化单体中的端口与适配器。每个上下文包含领域、应用、基础设施和 API 四层。

```text
presentation: FastAPI router / WebSocket gateway / CLI
       |
application: use case / transaction boundary / DTO mapping
       |
domain: entity / value object / state transition / port
       |
infrastructure: SQLAlchemy repository / 115/JavDB/DMM/AI adapter / filesystem
```

领域层不能 import FastAPI、SQLAlchemy、httpx 或具体 115 SDK。外部适配器不得直接修改领域实体，必须通过应用用例和合法状态转换。

### 3.4 目标目录结构

```text
backend/
  pyproject.toml
  src/sakuraplayer/
    identity/
    resources/
    catalog/
    discovery/
    cloud_cache/
    playback/
    events/
    shared/
    api/
    worker/
    scheduler/
    migrations/
  tests/
    unit/
    integration/
    e2e/
    fixtures/
  docker/

windows/
  lib/
    app/
    core/
    features/auth/
    features/library/
    features/rankings/
    features/actors/
    features/cache/
    features/playback/
    features/settings/
    routes/
    theme/
    widgets/
  test/
  integration_test/
  windows/

harmony/
  entry/src/main/ets/
    app/
    core/
    features/
    pages/
    components/
  entry/src/ohosTest/

contracts/
  generated/        # 从 OpenAPI 生成或校验的客户端模型，不手改
```

### 3.5 架构规则

1. API 路由只做认证、校验、用例调用和响应映射，不写业务状态机。
2. 所有任务领取、状态转换、容量计数和幂等键必须在 PostgreSQL 事务中完成。
3. 调度器只入队；worker 执行业务；API 不执行 600 秒元数据任务。
4. 元数据硬超时使用可终止的子进程，不用无法强制停止的线程 future。
5. 115 Cookie、AI 密钥、JavDB 密码和磁力正文只在最小作用域内解密，日志统一脱敏。
6. 任何 115 删除都必须重新验证账号、根 CID、任务 CID、当前父 CID 和数据库 owner。
7. `302` 播放入口不代理媒体字节，不在数据库或日志保存完整上游 URL。
8. Windows 和 HarmonyOS 不共享 UI 源码，只共享 OpenAPI、事件、错误码和固定 User-Agent 约定。
9. 客户端状态以 REST 快照为准，WebSocket 事件只用于降低刷新延迟。
10. 新增外部依赖、限界上下文或公共契约必须先更新架构文档并写 ADR。
11. 运行环境变量、启动级 secret、发布地址和客户端后端基址必须遵循 `contracts/runtime-configuration.md`，不得在任务内另起名称。

### 3.6 设计模式

| 模式 | 用途 | 示例 |
|---|---|---|
| Repository | 聚合持久化 | `MovieRepository`、`CacheJobRepository` |
| Unit of Work | 一次用例的事务边界 | 创建离线任务同时检查 2/10 上限 |
| Port/Adapter | 隔离非官方外部协议 | `Cloud115Port`、`MetadataProviderPort` |
| State Machine | 限制任务非法倒退 | 元数据、离线缓存、播放租约、清理 |
| Outbox/Event Log | 提交后推送状态 | 事务内写事件，WebSocket 按游标发送 |
| Process Supervisor | 600 秒硬超时 | 父 worker 管理元数据子进程组 |
| Snapshot | 排行榜和任务恢复 | 榜单最近成功快照、REST 任务快照 |
| Anti-Corruption Layer | 外部字段归一化 | AVdb CSV、JavDB、DMM、GFriends、115 |

### 3.7 API 约定

| 项目 | 约定 |
|---|---|
| 基础路径 | `/api/v1` |
| 认证 | `Authorization: Bearer <access-token>`；签名流入口使用会话绑定能力 URL |
| 内容类型 | JSON 使用 UTF-8；字幕下载保留安全 MIME |
| 错误 | `{code, message, details, request_id}`；`code` 稳定，`message` 不含秘密 |
| 分页 | 游标分页；`limit` 默认 24，最大 100 |
| 幂等 | 创建类请求接受 `Idempotency-Key`；重复键返回同一资源 |
| 时间 | RFC 3339 UTC；计划调度显式使用 `Asia/Shanghai` |
| 事件 | `{version,event_id,stream_version,type,occurred_at,resource}` |
| 播放 | 每次点击重新创建 12 小时签名会话；响应 `Cache-Control: no-store` |
| 首次初始化 | 尚无管理员时 `POST /auth/bootstrap` 要求 `X-Bootstrap-Token`；管理员存在后永久拒绝且不再校验该 header |
| 运行配置 | [runtime-configuration.md](001-sakuraplayer-v1/contracts/runtime-configuration.md) |
| AVdb 输入 | [avdb-source.md](001-sakuraplayer-v1/contracts/avdb-source.md) |
| 运维健康 | [operational-health.md](001-sakuraplayer-v1/contracts/operational-health.md)；内部探针不进入业务 OpenAPI |
| 目录/发现端口 | [catalog-discovery-ports.md](001-sakuraplayer-v1/contracts/catalog-discovery-ports.md)；Phase 1 不提前建立 cache/playback 表 |

### 3.8 已批准的参考代码接口

以下接口来自 `avmedia/sakuramediabe/src/lib/cloud115`，允许在保留 GPLv3 来源说明后移植。实现任务必须先用真实协议测试验证签名；不得凭名称猜测行为。

| 接口 | 已核验签名 | 用途 |
|---|---|---|
| `Cloud115Client.probe_cookies_status` | `async () -> Cloud115CookieStatus` | 区分有效、过期、上游不可用 |
| `Cloud115Client.snapshot_cookies` | `() -> str` | 持久化 `Set-Cookie` 合并结果 |
| `Cloud115Client.list_dir` | `async (cid, offset=0, limit=1000) -> (entries,total)` | 确认目录和分页枚举 |
| `Cloud115Client.mkdir` | `async (pid, name) -> str` | 创建专属根目录与任务目录 |
| `Cloud115Client.iter_files_recursive` | `async (cid, page_size=1000) -> AsyncIterator[DirEntry]` | 离线完成后递归解析文件 |
| `Cloud115Client.add_offline_urls` | `async (urls, save_dir_id) -> list[OfflineTaskAddResult]` | 用户点击后提交离线 |
| `Cloud115Client.list_offline_tasks` | `async (page, page_size) -> OfflineTaskPage` | 远端状态对账 |
| `Cloud115Client.delete_offline_tasks` | `async (info_hashes, delete_source_files) -> None` | 取消远端任务 |
| `Cloud115Client.get_download_url` | `async (pickcode, user_agent) -> DirectUrl` | UA 绑定原画直链 |
| `Cloud115Client.get_video_info` | `async (pickcode) -> VideoInfo` | HLS master 与清晰度列表 |
| `Cloud115Client.download_bytes` | `async (pickcode, user_agent, max_bytes) -> bytes` | 有上限地下载字幕 |
| `Cloud115Client.delete_files` | `async (fids, pid=None) -> None` | 通过安全清理器删除受管目录内容 |
| `Cloud115QrLogin.fetch_result` | `async (uid, app='alipaymini') -> QrLoginResult` | 扫码完成后换取 Cookie |

关键限制：获取直链或 HLS 时使用的 User-Agent 必须与播放器后续请求一致；同一原画 URL 的并发 Range 应保持接近 1，禁止突发 5 个以上请求。

## 4. 安全约束

### 4.1 阻断级规则

| 规则 | 依据 | 验证 |
|---|---|---|
| 密码使用 Argon2id，禁止明文/可逆密码 | CWE-916 | 密码模型与登录测试 |
| 首次管理员创建要求一次性 bootstrap token | CWE-306 | 缺失/错误/并发/已完成 bootstrap 测试 |
| Cookie/AI/JavDB 秘密使用 AES-256-GCM，主密钥不入库 | CWE-312 | 数据库扫描与密钥轮换测试 |
| 所有业务、管理、WebSocket 和签发端点需要身份 | CWE-306 | OpenAPI 安全扫描与 API 测试 |
| 签名播放 URL 校验资源 owner、会话 epoch、UA、模式和过期时间 | CWE-345 | 篡改/过期/撤销测试 |
| SQL 全部参数化 | CWE-89 | ORM 约束与静态扫描 |
| XML 禁用外部实体和网络解析 | CWE-611 | 恶意 actor-mapping 样本测试 |
| 下载资源校验期望资产名、大小上限和 SHA-256 | CWE-494 | 篡改资产测试 |
| 文件路径只接受服务端生成的相对路径 | CWE-22 | 路径穿越测试 |
| 115 删除必须通过目录归属证明 | CWE-862 | 移动目录、伪造 CID、跨账号测试 |
| 日志不得出现完整秘密或能力 URL | CWE-532 | 日志捕获回归测试 |
| 远程客户端使用 HTTPS 或可信加密 VPN | CWE-319 | Compose 发布地址与部署配置测试 |

### 4.2 令牌与加密

- 访问令牌默认 15 分钟；刷新会话默认 30 天，并保存哈希而不是明文刷新令牌。
- access/refresh 均为仅接受 HS256 的类型化 JWT；刷新会话保存当前 refresh JWT 的 SHA-256，30 天是登录时起的绝对期限，轮换不延长。
- 退出登录撤销 access JWT `sid` 对应的本机刷新会话并递增用户 `session_epoch`，旧 access 与播放签名随之失效；其他未撤销客户端可 refresh 到新 epoch。
- 加密记录保存 `key_id`、随机 96-bit nonce、ciphertext 和认证 tag；相同明文每次密文不同。
- 设置加密、JWT、播放 HMAC 和 bootstrap 使用不同 secret；Docker Secret 文件优先于环境变量。缺少任一必需密钥、格式错误或复用密钥时生产模式拒绝启动。
- bootstrap token 不入库，管理员创建后即使运行环境仍保留 token 也不能再次创建或替换管理员。
- 普通诊断只显示凭据状态和最后验证时间，不返回密文、摘要前缀或可复原值。

### 4.3 外部内容安全

- HTML 元数据只提取白名单文本字段，不在客户端渲染上游 HTML。
- GFriends 和图片 URL 只能来自固定 HTTPS 主机白名单。TASK-008 永久目录图片固定为 `https://c0.jdbstatic.com` 精确主机。
- TASK-009 的 Actor Mapping/Filetree 固定为精确 GitHub Raw URL，正文上限分别为 16/32 MiB，最多三跳逐跳校验重定向；GFriends Content URL 只能由固定基址和受校验相对段生成。
- Actor Mapping 使用 defusedxml 0.7.1 拒绝 DTD、实体和外部网络；GFriends 路径拒绝绝对路径、scheme、反斜杠和 `.`/`..` 路径段。
- 永久图片只接受 JPEG/PNG/WebP，单图最多 8 MiB、最多 3 次逐跳校验的重定向、单边最多 12,000 像素且总像素最多 40,000,000，使用 Pillow 11.2.1 完整解码后写入同目录临时文件并原子替换。
- OpenAI 兼容 `base_url` 由管理员配置，但连接测试与请求日志不得输出 API key。
- TASK-010 的 `ai.configuration` 加密载荷归身份与配置上下文所有；目录与元数据只通过 typed snapshot 消费，并在自身上下文保存 translation reservation/record。HTTP 调用前先持久提交 dispatched，未知付费结果不自动重派。
- 自动测试默认使用固定 fixture 和 fake adapter；真实外部测试必须显式标记。

## 5. AI 实现护栏

1. 功能规格是产品行为真相，数据模型和技术计划中的 `(derived)` 内容只是实现建议。
2. 修改前必须读取本架构、领域词汇和对应任务文件。
3. 只能使用 3.1 与 3.8 中锁定并验证的依赖/API；新增依赖先更新架构与 ADR。
4. 不得把 Redis、Celery、RabbitMQ、GraphQL、服务端视频代理或转码引入 v1。
5. 不得把 AVdb 来源帖子等同于影片，也不得把整个亚洲无码分类标为“破解”。
6. 不得让 DMM、GFriends、图片或 AI 失败阻止已完成 JavDB 核心元数据的影片展示。
7. 不得自动重试失败的元数据影片任务；只有管理员动作能创建新的尝试。
8. 不得为了测试而增加规格未要求的产品行为；补充测试只能列为非阻断验证。
9. 任何播放代码必须保留固定 UA、`302 no-store`、seek 合并和不代理视频字节四项约束。
10. HarmonyOS 功能实现必须等待 Windows 与真实 115 门禁完成；在此之前只允许契约探针和工程脚手架。
11. 不得让客户端在更换后端基址后继续使用旧服务端令牌、字幕或内存快照。
12. 共享工作区采用单写者，多智能体只做并行只读审计；审计结论由主实施路径统一修改。
13. 实施验证分为快速反馈与最终门禁两级；快速结果不能降低最终质量集合。
14. 质量门禁只能随功能和风险增加，不能因为耗时、并行或任务范围而减少。
15. 实施不得调用或依赖 Superpowers 插件及任何 `superpowers:*` 技能；仓库工作流本身定义规划、TDD、调试、审计、验证和 Git 收尾步骤。
16. 超过 5 次工具调用、多阶段或可能跨会话的任务继续使用 `planning-with-files-zh`，其本地规划记录不得替代正式任务或契约。
17. 排行榜 scheduler 只按 01:45 Asia/Shanghai 生成持久目标请求；JavDB 登录、分页、快照写入和 current 切换只在 worker 执行，API 只读本地 immutable snapshot。

具体测试命令、Compose 执行频次和任务内批次以
[统一实施与验证工作流](001-sakuraplayer-v1/implementation-workflow.md) 为准。
