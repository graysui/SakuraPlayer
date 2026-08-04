# SakuraPlayer v1 技术计划

**功能规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**项目架构**: [../architecture.md](../architecture.md)

**创建日期**: 2026-07-24

**状态**: Frozen for implementation

## 1. 技术目标

本计划定义如何从空仓库实现 SakuraPlayer v1。实现优先级严格为：后端契约与数据真相、元数据目录、115 缓存播放、Windows 客户端、真实 115 门禁、HarmonyOS 客户端。任何阶段都不得通过预取、服务器代理视频、多用户或永久 115 媒体库缩短实现路径。

### 1.1 输入依据

- 功能规格中的 25 组需求与 135 条验收条件。
- 真实 AVdb 快照：433,158 条总记录，六个目标分类 289,858 条。
- `contracts/avdb-source.md` 冻结的 AVdb 主备源、PBKDF2-HMAC-SHA256、AES-256-GCM 和 CSV 格式。
- `avmedia` 已验证的 115 Cookie、扫码、离线、直链、HLS、字幕下载和错误映射原语。
- `metadata-concurrency.md` 的三影片并发经验，但 v1 增加 600 秒父进程硬终止和禁止自动重试。
- Windows 播放器的 Player 层 seek 合并经验。

### 1.2 不变约束

1. 后端是外部协议唯一持有者，客户端永远拿不到 115 Cookie 或磁力正文。
2. PostgreSQL 是跨进程状态真相，WebSocket、调度器内存和客户端内存都可丢失并恢复。
3. 用户点击具体来源的播放按钮之前，不创建 115 离线任务。
4. 客户端最多阻塞等待 60 秒；60 秒与 600 秒分别属于客户端等待和元数据任务硬超时，不能混用。
5. 只有 JavDB 核心元数据成功的影片可见；DMM、图片、GFriends 和 AI 是非阻断富化。
6. Windows 与真实 115 核心链路未通过前，不进入 HarmonyOS 功能实施。
7. 首次管理员创建要求一次性 bootstrap token；设置 AES、JWT 和播放 HMAC 使用不同启动级密钥。
8. 客户端先配置并验证后端基址；更换服务端必须清空旧会话和本地字幕状态。

## 2. 技术栈

完整版本和升级规则以 [项目架构](../architecture.md) 3.1 为准。任务实现使用以下主链：

| 组件 | 选择 | 固定版本 | 选择理由 |
|---|---|---:|---|
| 后端 | Python / FastAPI | 3.10.16 / 0.110.1 | 可选择性移植参考项目中已验证的 async 115 和元数据代码 |
| 数据 | PostgreSQL / SQLAlchemy / Alembic | 17.5 / 2.0.41 / 1.16.2 | 行锁、部分唯一索引、持久队列和明确迁移 |
| 外部 HTTP | httpx | 0.28.1 | async 连接池、超时、测试 transport |
| 密码与秘密 | Argon2id / AES-256-GCM | argon2-cffi 23.1.0 / cryptography 45.0.4 | 分离不可逆密码和可恢复外部凭据 |
| Windows | Flutter / Riverpod | 3.29.2 / 3.1.0 | 桌面 UI 与单一状态方案 |
| 播放 | media_kit / libmpv | 1.1.11 / 1.0.5 打包版本 | 原画 Range、HLS、MKV、libass 与底层 seek 控制 |
| HarmonyOS | ArkTS/ArkUI/AVPlayer | API 24；DevEco Studio 6.1.1.290；SDK 包标记 6.1.1.125；Hvigor 6.24.3；ohpm 6.1.2.285；DevEco 内置 Node 18.20.1 | 用户指定的原生 HarmonyOS 基线与本机已安装工具链 |
| 部署 | Docker Compose | 2.37.1 | 单机私有部署，最少运维组件 |

### 2.1 禁止技术

| 技术或模式 | 不采用原因 | 已选替代 |
|---|---|---|
| Redis / RabbitMQ / Celery | 单管理员负载不值得增加恢复与运维面 | PostgreSQL 持久队列和事件表 |
| GraphQL | 页面契约稳定且需要简单的缓存/错误语义 | REST OpenAPI + WebSocket |
| 服务端视频代理/转码 | 会让 NAS 承担带宽与编解码，违背直链目标 | 签名入口 `302` 到 115/CDN |
| SQLite 生产部署 | 无法可靠表达并发 claim、部分索引和多进程互斥 | PostgreSQL 17.5 |
| Flutter HarmonyOS 移植 | 无法保证用户指定 API 24 原生播放行为 | ArkTS/ArkUI + AVPlayer |
| 外部播放器 | 无法可靠同步进度、UA 和生命周期 | 应用内播放器 |
| 后台自动离线/预取 | 违背用户明确触发原则 | 详情页来源选择 + 播放动作 |
| 全量 GFriends 镜像 | 约 27.9 万图片路径，浪费持久卷 | 服务端索引 + 客户端按需缓存 |
| 时间轴缩略图 | v1 明确排除 | 标准进度控制 |

## 3. 架构决策

### AD-001: 模块化单体加独立进程

**背景**: 系统有 API、定时调度、可硬终止元数据任务和 115 长任务，但只有单管理员负载。

**决策**: 一个后端代码库，部署 `api`、`scheduler`、`worker` 三个应用进程，共享 PostgreSQL 和领域模块。

**替代方案**:

1. 单进程 FastAPI：部署简单，但 600 秒任务终止、重启恢复和 API 响应隔离较差。
2. 多微服务：隔离更强，但契约、部署和事务复杂度不符合单用户产品。

**后果**: 领域代码可复用，进程职责清楚；必须使用数据库协调，不能依赖进程内锁。

### AD-002: PostgreSQL 作为任务队列

**背景**: 元数据与缓存任务必须重启恢复、固定并发、可观察且数量不大。

**决策**: 任务表保存优先级、状态、claim owner/expiry、尝试和错误；worker 用 `FOR UPDATE SKIP LOCKED` 领取。

**替代方案**:

1. Redis 队列：吞吐更高，但增加持久一致性和运维组件。
2. APScheduler job store 直接跑业务：调度记录不足以表达领域状态机。

**后果**: 事务可以同时保证容量和幂等；需要维护 claim 续租与崩溃回收。

### AD-003: 元数据任务使用可杀死子进程

**背景**: Python 线程不能安全强制终止，用户要求超过 600 秒必须终止。

**决策**: 元数据 supervisor 固定最多启动 3 个子进程。每个子进程处理一部影片，父进程以单调时钟计时并终止整个进程组；事务外下载、事务内短提交。

**替代方案**:

1. `asyncio.wait_for`：只能取消协程，阻塞解析器或线程可能继续运行。
2. 线程池 future：无法硬杀线程。

**后果**: 可满足硬超时，但 provider 和数据库会话不能跨进程共享；子进程必须幂等写入。

### AD-004: 核心元数据与富化分阶段提交

**背景**: JavDB 成功即可展示，DMM、图片、GFriends、AI 失败不能阻断。

**决策**: 一次元数据尝试记录多个 stage。JavDB 核心聚合在短事务提交并设置 `core_ready`；后续 stage 写各自结果和 warning。任务最终为 `completed`、`completed_with_warnings` 或 `failed`。

**后果**: 已可见影片不因可选源故障回滚。若 600 秒在核心提交后触发，任务记 `failed`，影片仍保持 `core_ready`，管理员可手动重试缺失阶段。

### AD-005: 来源帖子与影片分离

**背景**: 同一番号有多个格式/大小/分类来源，部分来源没有番号，部分来源需永久拒绝。

**决策**: `resource_source` 以 `website + tid` 唯一；`movie` 以规范化番号唯一；关系允许多个来源指向一部影片。来源标签可叠加。

**后果**: 详情页可像 Emby 一样选择来源，不会把中文字幕、破解、4K、有码做成互斥分类。拒绝单条来源不会删除影片。

### AD-006: 115 每任务独立目录与证明式删除

**背景**: 系统绝不能误删用户其他 115 内容，用户可能手动移动或删除任务目录。

**决策**: 首次绑定创建 `SakuraPlayer-Cache`。每个任务创建随机独立子目录并保存 CID。删除前重新验证绑定账号、根 CID、任务 CID、当前 parent CID 和数据库 owner。

**后果**: 目录移动后标记 `detached`，不追踪删除；清理失败不释放容量并可手动重试。

### AD-007: 原画优先的能力 URL

**背景**: 115 上游 URL短期且绑定 User-Agent，客户端不能持有 Cookie，NAS 不能代理视频。

**决策**: 已认证接口为完整有序媒体选择创建 12 小时播放会话，签名绑定管理员 session epoch、平台 UA、缓存、媒体和模式。流入口校验后解析上游地址并返回 `302 no-store`。TASK-108 默认且只解析原画；TASK-109 才在可回退失败或用户选择兼容播放时解析最高码率 HLS。能力 URL 严格按 Cloud115Port 契约校验；TASK-213 只按 [Cloud115 能力域兼容边界](changes/2026-07-31--task-213-cloud115-capability-host-compatibility.md) 增加真实观察到的 `*.115cdn.net` HTTPS 子域。

**后果**: 上游 URL 不落库。播放器必须固定 UA 并合并 seek；用户切换兼容模式会创建新会话。

### AD-008: 事件通知采用持久日志加 REST 快照

**背景**: WebSocket 可能断线，客户端完全退出后不常驻。

**决策**: 领域事务同时写版本化事件。数据库生成全局单调 sequence 作为追赶水位，`event_id` 用于去重，`stream_version` 用于聚合合并。WebSocket 推送事件；首次连接、重连或游标过旧时获取同一事务水位下的有界 REST 快照。事件 resource 按类型化字段浅合并，本地无资源或版本跳号时必须拉快照。快照资源不暴露聚合版本；客户端把它标记为未知基线，无游标重放时忽略水位前事件，并以水位后的第一条同资源合法事件建立版本基线。

**后果**: 不需要保证 WebSocket 逐条不丢；事件与精简通知固定保留 30 天，客户端不能把事件当最终状态。快照返回活动/近期状态、最新 100 条未读通知和汇总计数，不承担无限历史导出；ready 通知不得自动播放。

### AD-009: 两端只共享契约

**背景**: Windows 要先交付，HarmonyOS 使用原生 ArkUI/AVPlayer，平台交互不同。

**决策**: OpenAPI、事件 schema、错误码、状态机语义和固定 UA 是共享资产；UI、状态容器、播放器封装分别实现。

**后果**: HarmonyOS 不受 Flutter 运行时限制，但必须通过契约 fixture 保持行为一致。

## 4. 后端执行设计

### 4.1 AVdb 同步

```text
GitHub Release API
  -> 主源发现，失败再尝试备用源
  -> 下载到临时文件并计算 SHA-256
  -> 读取 manifest 并校验算法/迭代/长度
  -> PBKDF2-HMAC-SHA256(200000) 派生密钥
  -> AES-256-GCM 认证解密
  -> 内层 ZIP/CSV 流式读取
  -> 六分类过滤、字段校验、番号规范化、标签推导
  -> 分批 upsert source + 记录拒绝命中
  -> 提交同步游标和统计
```

- 每天 03:00 Asia/Shanghai 导入 30D 包。
- 每周日 04:00 对全量包做插入与更新，不删除缺失旧来源。
- 主源与备用源若发布同名资产，导入前摘要必须一致；不一致时停止并报警。
- Release 资产名只接受冻结前缀/计数以及既有 8 至 14 位紧凑数字或官方现行
  `YYYY-MM-DD-HH-MM-SS` 时间戳；TASK-213 真实门禁不得通过关闭全名白名单绕过上游命名漂移。
- manifest 继续拒绝未知字段；官方现行公开信封声明只允许固定 format/version/payload 和完整白名单
  original filename，四项必须成组出现，且不得放宽 GCM、摘要或 ZIP/CSV 校验。
- 单批默认 1,000 行 `(derived)`，失败只回滚该批；同步批次记录成功、失败和跳过数。
- 首批元数据选择最近 90 天最多 5,000 个唯一番号；之后按发布日期持续历史补齐。

### 4.2 元数据优先队列

优先级由小到大执行：

| 优先级 | 来源 |
|---:|---|
| 10 | 管理员手动重试、用户搜索缺失影片 |
| 20 | 排行榜命中但缺少核心元数据 |
| 30 | 每日新增 AVdb 资源 |
| 40 | 首批最近 90 天 |
| 50 | 历史补齐 |

同优先级按影片发布日期降序、任务创建时间升序。队列不设总量上限，运行槽固定 3。一个编号同时只允许一个 `queued/running` 尝试。

单任务阶段：

```text
normalize/check
  -> JavDB search/detail
  -> core transaction: Movie/Actor/Tag/relations + core_ready
  -> permanent image downloads
  -> DMM description
  -> actor mapping / GFriends index association
  -> AI translation enqueue or reuse
  -> completed / completed_with_warnings
```

HTTP 层允许在单次 provider 请求内部对 `408/429/5xx` 做有限瞬时重试 `(derived)`，但影片任务失败或超时后绝不自动创建新任务尝试。

### 4.3 115 缓存状态机

```text
queued
  -> submitting
       |-> offlining -> resolving
       |                 |-> awaiting_selection -> ready
       |                 \-> ready (可自动识别主视频)
       \-> submit_uncertain -> cancelling
                                \-> submit_uncertain (对账仍无唯一匹配，不自动重提)

queued/submitting/offlining/resolving -> cancelling -> cleaning -> cleaned
任一执行态 -> failed
ready -> cleaning -> cleaned
cleaning -> cleanup_failed -> cleaning (仅手动或维护重试)
受管目录证明失效 -> detached
```

规则：

- 创建时先复用同来源的活动任务，再在事务内检查运行 2、排队 10。
- 获得运行槽的响应为 `started`，客户端进入全屏等待；排队响应为 `queued`，客户端立即退出等待。
- 60 秒只由客户端倒计时。倒计时结束不写任务失败状态。
- worker 提交前创建任务目录。115 返回的 `info_hash` 与本地任务 ID 分开保存。
- worker 在外部提交前持久化 `submit_started_at`；结果不确定且对账无唯一匹配时进入
  `submit_uncertain`，保留 running 容量并禁止自动重提。
- 完成后按 [TASK-105 媒体解析确定性边界](changes/2026-07-27--task-105-media-resolution-determinism.md)
  有界递归枚举视频和字幕；视频最低 256 MiB（包含边界），白名单、广告/样片词元、连续分段、
  可解释评分和保守自动选择规则由固定 fixture 验证。
- 多个无法确定主文件的候选进入 `awaiting_selection`，客户端选择后才 `ready`；两者都属于
  materialized cache，在首次进入时初始化服务端 TTL。
- 默认 TTL 24 小时，可配置 1 到 168 小时；设置变更只影响新缓存和下一次成功创建播放会话的
  刷新，不批量改写已有缓存。
- ready capacity 以 20 为安全删除后的收敛目标；TTL 到期优先，容量 LRU 再按
  `last_accessed_at NULLS FIRST, ready_at NULLS FIRST, created_at, id` 从无租约的
  `awaiting_selection/ready` 中稳定选择。清理中或失败的缓存继续占容量。
- TASK-107 创建 lease 外键所需的最小 playback session Schema；TASK-108 独占签名和会话 API。
- TASK-112 在 worker 启动时复用同一 claim-fenced offline/resolver/cleanup pipeline 做最多 100 次
  有界恢复 drain；领取事务提交后才访问 115。`submit_uncertain`、materialized 和终态不自动倒退。

### 4.4 播放和字幕

1. 客户端调用已认证的播放会话接口，提交就绪缓存和媒体选择。
2. 后端生成绑定固定 UA 和模式的签名入口；默认 `original`。
3. 播放器请求入口，后端校验 HMAC、过期时间、session epoch、owner、媒体仍受管、请求 UA。
4. 原画模式调用 `get_download_url(pickcode, same_ua)`；只有
   `cloud115_original_unavailable` 自动回退 HLS，凭据、文件不存在、限流、上游不可用和协议错误
   均保持原错误。
5. 兼容模式直接调用 `get_video_info`；Cloud115 适配器解析 master 并校验能力 URL，播放层只
   校验类型化 DTO 并选择 bandwidth 最大的 variant，同码率选择 master 中首项。
6. 返回 `302` 和 `Cache-Control: no-store`，不保存上游 URL；每个并发 stream 请求独立解析能力
   URL，避免多个 Range 共享同一条存在并发额度的上游直链。
7. 客户端从已认证字幕接口下载最多 8 MiB `(derived)` 的 `.srt/.ass/.ssa/.vtt` 到应用私有缓存并交给播放器。

Windows 的 Player 包装器覆盖 `seek`：已有 seek 在飞时只保留最后目标，完成后再执行；失败清空 pending
并向 controller 返回错误。ready job/首媒体 typed route、候选组选择、同 origin capability、
media_kit `http-header-fields` 固定 UA、过期重签和所有 seek 入口由
[Windows 播放器客户端契约](contracts/windows-playback-client.md) 冻结。HarmonyOS 在 AVPlayer 上
实现等价串行 seek 队列，使用 API 24 SDK 签名核验和契约 fixture 验证 Range、302 和 HLS 子请求 UA。TASK-213 的真实
Range 证据按 [Range seek 证据串行化](changes/2026-08-01--task-213-range-seek-evidence-serialization.md)
与生产 in-flight 合并一致地顺序执行，每次仍独立请求 stream 入口；后端并发请求独立签发责任不变。

### 4.5 播放进度

- 后端以 `movie_id` 唯一保存位置、时长、完成状态和版本。
- 客户端播放期间每 15 秒 `(derived)` 发送心跳，可附带进度；暂停、退出、完成立即 flush。
- 请求 `version` 是 expected current version：首次写入使用 0，成功后服务端从 1 开始递增；旧版本或
  未来版本均返回 `409 progress_version_conflict` 和权威进度，且不得部分续租。
- 未知时长显式提交 `duration_seconds=null`，只保存位置且不完成；位置 0 不完成。已知时长时达到
  95% 或严格剩余 `<120` 秒完成，恰好 120 秒不完成，完成后权威位置归零。
- 无 progress 心跳只续租并刷新 TTL；`playing=false` 可原子 flush 后结束 lease，不续期 TTL。
- 未完成进度自动 seek，不弹选择框。
- 达到 95% 或剩余不足 120 秒时写 `completed=true` 和位置 0；下次从头。
- 播放按钮从影片级进度派生环形/条形进度或已看完标记。

### 4.6 排行榜和发现

- JavDB 同步写不可变快照头和有序条目，全部成功后原子切换 `current_snapshot_id` `(derived)`。
- scheduler 每天 01:45 Asia/Shanghai 为每个目标持久入队；worker 以 claim token/lease 执行。日/周/月固定使用公开 playback all 榜；TOP250 同步总榜和当前年，2008 至上一年只在缺少 current 时补一次。
- 页面读取日榜、周榜、月榜、TOP250；年份只对 TOP250 查询生效，null 表示总榜，显式年份为 2008..服务器当前年。
- 条目保留原始 rank，非法番号跳过、重复番号只保留首次。若存在 AVdb 来源但影片未 `core_ready`，幂等创建或提升优先级 20 任务；查询只返回已有来源且 `core_ready` 的影片。
- 同步失败保留 current 指针，不清空最近成功快照。
- cursor 绑定 immutable snapshot ID；翻页期间 current 切换不混合结果。空或全无效 provider 响应按失败处理。
- 番号精确搜索先查本地规范化列；命中 raw source 但无影片时创建优先级 10 任务并返回补全占位状态。

## 5. 客户端设计

### 5.1 Windows

Windows 使用 feature-first Flutter：

```text
AppShell
  left navigation: 媒体库 / 排行榜 / 女优
  top bar: 搜索 / 缓存状态 / 设置
  content: typed routes

Riverpod controller
  -> generated/validated API DTO
  -> Dio API client
  -> immutable view state
```

- 媒体库为去重影片网格，筛选与滚动位置只保存在本机页面状态。
- 首次登录前配置/测试后端基址；远程 HTTP 只允许私有地址并显式确认风险，HTTPS 不允许忽略证书错误。
- 影片详情聚合基础资料、永久图片、演员、收藏、影片进度和来源列表；来源列表按标签、资源大小和可用状态扫描。
- 点击来源播放后，根据响应选择全屏等待、排队提示或直接播放器。
- 全屏等待只允许二次确认取消；应用在 60 秒内仍通过事件/快照更新进度。
- 歧义媒体在缓存页按候选组选择完整有序分段；ready 缓存只在用户显式动作后进入携带 job/首媒体
  UUID 的播放器 route，后台 ready 或通知不自动播放。
- 播放器只有原画/兼容播放、字幕、音轨、倍速、全屏和标准进度控制；内嵌字幕/音轨由客户端播放器枚举，后端 manifest 只发布已选媒体队列授权的外置字幕及私有缓存期限。
- 主题默认跟随系统，播放器固定深色；桌面使用左侧导航和窗口最小尺寸约束 `(derived)`。

### 5.2 HarmonyOS

- 主页面使用底部导航：媒体库、排行榜、女优。
- 登录前使用与 Windows 相同的后端基址校验规则，更换地址后清空 Asset Store 中的旧会话。
- 使用系统安全存储保存刷新令牌，应用私有目录缓存字幕和 GFriends 图片。
- AVPlayer 适配器必须显式设置固定 UA，处理 `302`、Range、HLS、MKV、内嵌字幕/音轨与外置 ASS。
- 系统后台仅使用平台允许的通知与生命周期，不建设常驻下载服务；115 离线在后端继续。
- 功能任务在 Windows 真实门禁和 TASK-301 API 24 SDK/构建基线后开始，之前只建立空工程、契约测试和播放 fixture；不要求连接物理真机。

## 6. 实施阶段

### Phase 1: 基础与资源目录

**目标**: 建立可部署、可迁移、可认证的后端，完成 AVdb 导入和核心元数据可见链路。

**里程碑**:

- Docker Compose、loopback 默认发布、健康检查、PostgreSQL、Alembic Schema 门禁。
- 一次性 bootstrap token、唯一管理员、刷新会话、用途分离的启动密钥和脱敏错误。
- AVdb 主/备源、解密、六分类全量/增量幂等导入。
- 三并发/600 秒元数据 supervisor、JavDB 核心、DMM/GFriends/AI 富化。
- 永久图片卷、媒体库/搜索/影片/女优/排行榜 REST。

**完成门禁**: 固定 AVdb fixture 可重复导入；5,000 首批范围可证明；只有 `core_ready` 影片可见；进程重启可恢复任务。

### Phase 2: 115 缓存与播放后端

**目标**: 使用 Fake 115 完成从点击来源到播放、字幕、进度和安全清理的闭环。

**里程碑**:

- 单 115 扫码绑定、Cookie CAS 加密回写和专属根目录。
- 2 运行/10 排队、60 秒观察语义、任务复用、取消和后台继续。
- 文件/字幕解析、主视频选择、分段队列、24 小时 TTL、20 LRU。
- 12 小时能力 URL、原画/HLS、`302 no-store`、播放租约。
- WebSocket 事件、REST 快照、诊断与稳定错误码。

**完成门禁**: 按 [115 缓存播放后端 E2E 契约](contracts/backend-cloud115-e2e.md) 通过状态化 Fake 115 故障矩阵与生产服务组合；任何根目录外删除被拒绝；数据库无短期 URL或字幕正文。60 秒客户端倒计时和 UI 自动播放决策仍由客户端任务验证。

### Phase 3: Windows 客户端

**目标**: 交付 Windows 10/11 私有安装包和完整用户主链路。

**里程碑**:

- 登录/扫码、桌面 Shell、媒体库、搜索、排行榜、女优和详情。
- 来源选择、全屏等待、队列/缓存状态、系统通知和设置诊断。
- media_kit 原画/HLS、seek 合并、字幕/音轨、影片进度。
- Flutter 单元/Widget/集成测试和 Windows release 构建。

**完成门禁**: 自动测试通过，并用真实 115 完成 AC-130 的扫码、离线、原画、HLS、Range seek、字幕和清理。TASK-213 本轮可按 [外置字幕真实证据豁免](changes/2026-08-01--task-213-external-subtitle-evidence-waiver.md) 以显式、脱敏的操作者批准记录替代 `.srt` / `.ass` 真实样本下载；默认字幕门禁与产品能力不放宽。

### Phase 4: HarmonyOS 客户端

**目标**: 在 Windows 门禁后交付 API 24 原生侧载客户端。

**进入条件**: Phase 3 完成且 TASK-301 的 API 24 SDK 签名、构建和 fixture 基线通过；固定 UA、302、Range、HLS、MKV、ASS 的自动化验证由对应功能任务完成。

**里程碑**:

- ArkTS 网络/认证/事件基础设施和底部导航。
- 媒体库、排行榜、女优、详情、设置与缓存状态。
- AVPlayer 播放、字幕、音轨、进度、通知和私有缓存。
- ohosTest、契约 fixture、自动化 E2E 和开发者签名侧载产物；物理真机连接不属于进入条件。

## 7. 性能与容量

| 操作 | 目标 | 测量方式 |
|---|---:|---|
| 已缓存媒体库/榜单/女优 API | p95 < 500 ms | PostgreSQL fixture + API 计时 |
| 番号精确搜索 | p95 < 300 ms | 29 万来源规模压测 |
| 标题/别名模糊搜索 | p95 < 800 ms | `pg_trgm` 索引压测 |
| 事件提交到前台 | p95 < 2 s | 事件时间戳与客户端接收时间 |
| 播放入口本地校验 | p95 < 200 ms，不计 115 | mock 115 API 计时 |
| AVdb 导入 | 29 万级流式/分批 | 峰值内存、批次成功率、吞吐日志 |
| 普通列表限制 | 最大 100 条/请求 | OpenAPI 和边界测试 |

单用户基线压测使用 1 个管理员、2 个客户端、3 个元数据子进程、2 个离线任务和 29 万来源记录。目标不是高 RPS，而是数据量下的稳定延迟和内存上界。

### 7.1 资源预算 `(derived)`

| 组件 | 正常目标 | 告警阈值 |
|---|---:|---:|
| API 容器 | < 512 MiB | 768 MiB |
| Worker 父进程及 3 子进程 | < 2 GiB | 3 GiB |
| Scheduler | < 256 MiB | 384 MiB |
| PostgreSQL 连接 | 总计 <= 30 | 25 活跃连接 |
| 永久图片卷 | 可观测增长 | 80% 磁盘占用 |

## 8. 可观察性

结构化日志公共字段：`request_id`、`task_id`、`movie_id`、`movie_number`、`source_id`、`cache_job_id`、`stage`、`error_code`、`elapsed_ms`。外部 URL 只记录主机和路径模板，不记录 query。

| 指标 | 触发条件 | 动作 |
|---|---|---|
| 元数据 running 数 | 不等于 0..3 | worker 停止领取并报警 |
| 元数据超时 | 任一任务 600 秒 | 终止进程组、标记失败、等待手动重试 |
| 115 running/queued | 超过 2/10 | 拒绝创建并记录不变量错误 |
| Cookie 状态 | expired | 推送重新扫码；不把 unavailable 当 expired |
| 清理失败 | 连续失败或超过 24 小时 `(derived)` | 诊断页高亮，保留容量占用 |
| 事件游标落后 | 超过保留窗口 | 要求客户端拉 REST 快照 |
| 外部源错误率 | 10 分钟内 > 50% `(derived)` | 降低请求并显示富化 warning，不隐藏核心影片 |

## 9. 风险

| 风险 | 可能性 | 影响 | 缓解 | 最晚验证 |
|---|---|---|---|---|
| 115 非官方协议变化 | 高 | 高 | 独立适配器、fixture、真实显式集成、稳定错误映射 | Phase 2/3 |
| 原画 URL 的 UA/Range 行为变化 | 中 | 高 | 固定 UA、seek 串行、302 观测、真实 seek 测试 | AC-130 |
| HarmonyOS AVPlayer 子请求改写 UA | 中 | 高 | 先做 API 24 SDK 签名核验与契约 fixture，失败阻断相关功能实现 | AC-131 |
| AVdb 资产格式或密钥参数变化 | 中 | 高 | manifest 白名单、GCM 认证、摘要、保留最近成功游标 | Phase 1 |
| JavDB 限流或结构变化 | 高 | 中 | 固定并发 3、超时、核心任务可手动重试、provider fixture | Phase 1 |
| 600 秒终止时留下部分数据 | 中 | 中 | 核心短事务、stage 幂等、父进程对账 | Phase 1 |
| GFriends 名称歧义误关联 | 中 | 中 | 只接受唯一权威别名匹配，歧义直接丢弃 | Phase 1 |
| 任务目录被用户移动 | 中 | 高 | parent CID 重新验证，标记 detached，不追踪删除 | Phase 2 |
| 用户未配置自动备份 | 中 | 高 | 设置页明确显示无备份；文档声明已接受风险 | 发布 |
| 成人/版权合规 | 因地区而异 | 高 | 私有部署、无商店发布、用户承担适用法律和条款责任 | 发布 |
| 局域网抢占首次管理员或明文传输 | 低到中 | 高 | 一次性 bootstrap token、loopback 默认发布、远程 HTTPS/VPN | Phase 1 |

### 9.1 高风险响应流程

1. 通过稳定错误码和任务 stage 确认是协议、凭据、数据还是本地状态问题。
2. 停止新任务领取，不修改既有成功快照和就绪缓存。
3. 使用固定 fixture 复现；涉及 115 时在专用测试目录运行显式真实集成。
4. 更新适配器与契约测试，不在领域层加入站点特判。
5. 对受影响任务由管理员手动重试；禁止批量隐式重跑付费/限流操作。

## 10. 质量门禁

### 10.1 执行级别

下面的分层只优化反馈顺序，不改变本节质量矩阵的最终下限。具体步骤见
[统一实施与验证工作流](implementation-workflow.md)。

实施不得调用或依赖 Superpowers 插件及任何 `superpowers:*` 技能；复杂任务的持久规划继续使用 `planning-with-files-zh`。下述测试驱动循环、分层门禁和审计均由仓库工作流定义，与外部工作流插件无关。

| 级别 | 进入条件 | 内容 | 退出条件 |
|---|---|---|---|
| Focused | 单个实现批次有失败测试或待验证分支 | 受影响的单元、契约、静态检查和必要的 PostgreSQL 集成 | 批次行为稳定，未扩大跳过范围 |
| Fast | 当前任务所有实现批次完成 | 最大合理的自包含测试子集、聚焦 PostgreSQL、格式/lint/类型、完整 diff 和 `git diff --check` | 可进入只读审计；失败则回到实现循环 |
| Final | Fast、完整自审和只读审计收敛，P0/P1 已关闭 | 完整自动测试、真实 PostgreSQL、完整 Compose、认证/秘密扫描、重启/ready 降级恢复、资源清理及任务要求的外部门禁 | 产生当前任务可提交的完整证据；失败后修复并重新 Fast/审计 |

每次 Final 尝试最多运行一次完整 Compose。Final 失败不能沿用失败前的局部结果；修复后必须重新通过受影响的 Fast 和审计，再发起新的 Final 尝试。

| 门禁 | 要求 |
|---|---|
| Schema | 全新库升级到 head；旧/未知 Schema 明确拒绝启动 |
| 单元 | 状态机、番号、标签、TTL/LRU、签名、进度阈值全覆盖 |
| 数据库集成 | claim、2/10 上限、幂等、部分唯一索引、事件事务 |
| Provider | 固定样本覆盖成功、找不到、限流、结构变化和可选失败 |
| 安全 | bootstrap 抢占、密钥复用、凭据脱敏、传输边界、XML XXE、路径穿越、签名篡改、目录越界 |
| Fake E2E | 浏览 -> 来源 -> 离线 -> 解析 -> 播放 -> 字幕 -> 清理 |
| Windows | analyze、test、integration_test、release build |
| 真实 115 | 仅显式运行，覆盖 AC-130；TASK-213 本轮外置字幕证据仅按批准 Delta 显式跳过 |
| HarmonyOS | Windows 门禁后，API 24 SDK/构建/fixture 基线和 AC-131 先通过 |
| 许可证 | GPLv3、第三方声明、移植来源随产物 |

## 11. 技术计划摘要

| 决策 | 选择 |
|---|---|
| 后端形态 | 模块化单体，API/Scheduler/Worker 独立进程 |
| 数据和队列 | PostgreSQL 17.5，不引入独立消息系统 |
| 元数据硬超时 | 3 个可杀死子进程，600 秒，失败不自动重试 |
| 115 | 单绑定、独立任务目录、2 运行/10 排队、证明式删除 |
| 播放 | 12 小时能力入口、原画优先、最高 HLS 兼容、302 直连 |
| Windows | Flutter + media_kit/libmpv，先交付 |
| HarmonyOS | ArkTS/ArkUI + AVPlayer，API 24 SDK/构建/fixture 基线后实施 |
| 私有连接 | loopback 默认；客户端配置基址，远程使用 HTTPS 或可信 VPN |

下一步按四个实现工作流生成任务，每个工作流不超过 15 个实现任务，并为每个工作流追加独立 E2E 与代码清理任务。
