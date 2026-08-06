# SakuraPlayer v1 新会话交接

**更新时间**: 2026-08-06

**当前阶段**: TASK-325 completed：AI 配置恢复、翻译瘦身与 Docker 原地升级。下一任务 TASK-326。

## 1. 当前成果

- 功能规格包含 150 条验收条件，需求到任务的映射见 `traceability-matrix.md`。
- 技术计划采用 FastAPI、PostgreSQL、Docker、Flutter Windows 和 HarmonyOS API 24 原生客户端。
- 78 个有效任务覆盖后端元数据、115 缓存播放、Windows、HarmonyOS、运行修复和独立发布工作；另保留 1 个已撤销的 TASK-312 历史记录。
- OpenAPI、WebSocket、错误码、115 端口、元数据提供方、运行配置和 AVdb 数据源契约均在 `contracts/`。
- Windows 真实 115 门禁通过后，才建立 HarmonyOS 最小 Stage 工程；API 24 SDK 签名、构建和 fixture 基线通过后才实施鸿蒙业务功能，不要求连接物理真机。
- TASK-001 已交付 Python/FastAPI 后端骨架、显式 Alembic 迁移、Schema 启动门禁、五服务 Compose、四个持久化数据目录和内部健康检查。
- 启动配置固定四用途 secret，生产三类进程缺失、格式错误、来源冲突或用途复用时拒绝启动；bootstrap secret 生命周期由已接受变更规格冻结。
- TASK-001 自动验证覆盖 44 项启动测试、14 项 PostgreSQL 集成测试、四组件健康、持久日志、重启恢复、ready 故障降级和项目级 Docker 资源清理。
- TASK-002 已交付唯一管理员、Argon2id 密码、类型化 JWT、可撤销 refresh 会话、统一 HTTP/WebSocket 授权依赖和 logout epoch 清理语义。
- 认证契约冻结 15 分钟 access、登录起 30 天 refresh 绝对期限、同客户端单活、重放撤销、条件 bootstrap header 与 43..512 字符规范 Base64URL 初始化口令。
- TASK-002 自动验证覆盖 95 项自包含测试、18 项 PostgreSQL 集成测试、真实认证 canary、敏感日志扫描、重启恢复、ready 故障降级和项目级 Docker 资源清理。
- TASK-003 已交付 AES-256-GCM 加密 envelope、内存测试 key provider、`encrypted_setting` PostgreSQL 仓储和版本 CAS，以及统一日志/API 错误脱敏。
- 加密记录使用独立设置密钥、随机 96-bit nonce、key ID、密文和版本；并发新建/更新均以数据库原子条件写入避免旧凭据覆盖新值。
- 脱敏覆盖多段 Cookie、磁力、Bearer/JWT、AI key、client secret、DSN、绝对/相对 URL query、异常 traceback 与结构化日志字段；异常 code 仅允许稳定小写蛇形码。
- TASK-003 自动验证覆盖 125 项自包含测试、21 项 PostgreSQL 集成测试、Compose 真实认证 canary、秘密日志扫描、服务重启、ready 故障降级恢复和资源清理。
- TASK-004 已交付 AVdb Release 主备发现、逐跳下载校验、PBKDF2/AES-GCM 文件式解密、类型化 13 字段行流、同步事实、租约恢复、调度生产者和 worker consumer 端口。
- AVdb request/run 使用 token、未过期租约和 PostgreSQL 行锁隔离旧 worker；同 Release 已提交目录按文件集合、大小和 SHA-256 安全复用，解密明文使用受管目录并支持崩溃后扫尾。
- TASK-004 自动验证覆盖 175 项自包含测试、28 项 PostgreSQL 集成测试、迁移、五服务健康、认证 canary、敏感日志扫描、重启、ready 降级恢复和资源清理。
- TASK-005 已交付六分类流式来源导入、标准/FC2 番号规范化、去重影片骨架、90 日历日/5000 唯一番号首批范围、无上限历史候选和待识别管理员关联。
- `resource_source` 以 `(website, external_post_id)` 唯一，磁力以 AES-GCM envelope 保存；全量同步仅 upsert 当前行，缺失的既有来源不删除、不禁用。待识别 API 使用字面搜索、绑定状态与查询的键集游标，响应不暴露磁力或上游载荷。
- TASK-005 自动验证覆盖 199 项自包含测试、35 项 PostgreSQL Fast 测试、289,858 行流式容量证据，以及 Compose Final 的 41 项完整测试、服务健康、迁移、重启和清理。
- TASK-006 已交付来源证据化叠加标签、事务性影片合并/拆分、安全管理员响应，以及 Resources 所有的 `SourceRejectionPort`。
- 来源拒绝会原子清空磁力 envelope 并保存不含敏感载荷的唯一事实；导入与拒绝使用同一来源事务锁，增量/全量同步不能复活已拒绝来源。
- TASK-006 自动验证覆盖 204 项自包含测试、45 项 PostgreSQL 集成测试、17,202 条破解分类基线、并发拒绝/导入、迁移、五服务健康、重启、ready 降级恢复、秘密扫描和资源清理。
- TASK-007 已交付 PostgreSQL 持久元数据 job/stage、固定三槽 supervisor、600 秒 Linux 进程组硬终止、五级优先级、initial/history 持久 seeder，以及完整/可选富化管理员 retry。
- 元数据 child 独立创建 Engine/Session/httpx Client；provider 未交付时任务保持 queued。失败不会自动重试，initial 配额在多 worker 下严格不超过 5000，失败前缀通过候选 anti-join 不阻塞 history。
- TASK-007 自动验证覆盖 246 项自包含测试、33 项 PostgreSQL Fast 测试、三路无 P0/P1/P2 只读审计，以及 Compose Final 的 63 项 PostgreSQL/运行测试、迁移、五服务健康、重启、ready 降级恢复、秘密扫描和资源清理。
- TASK-008 已交付 JavDB 精确番号核心导入、Actor/Tag 关系、DMM 纯文本简介富化、可选 AES-GCM 凭据和永久目录图片原子缓存。
- JavDB 核心短事务与 DMM/图片可选阶段隔离；图片仅允许精确 HTTPS 主机和三种格式，并限制 8 MiB、3 跳、12,000 单边和 40M 总像素，失败保留最近 ready 图片并进入显式富化重试。
- TASK-008 自动验证覆盖 293 项自包含测试、38 项 PostgreSQL Fast 测试、三路无剩余 P0/P1/P2 只读审计，以及 Compose Final 的 67 项 PostgreSQL/运行测试、迁移、五服务健康、重启恢复和资源清理。
- TASK-009 已交付 Actor Mapping 与 GFriends 安全周更快照、权威别名协调、唯一演员 URL 索引、最近成功回退、持久调度请求和 worker claim/lease consumer。
- Actor Mapping 固定 16 MiB、defusedxml/XXE 拒绝和 JavDB 身份边界；GFriends 固定 32 MiB、三层安全路径与唯一匹配，只保存 URL 索引，不进入永久 `catalog_image` 或镜像 Content 图片。
- TASK-009 自动验证覆盖 342 项自包含测试、PostgreSQL 生命周期/并发聚焦测试和无剩余 P0/P1/P2 只读审计，以及 Compose Final 的 71 项 PostgreSQL/运行测试、迁移、五服务健康、重启恢复、秘密扫描和资源清理。
- TASK-010 已交付单载荷加密 AI 配置、固定单字段 OpenAI-compatible JSON 协议、protected 字段校验、持久付费 reservation/dispatch 事实和 metadata translation stage。
- 翻译以 owner/source/model/prompt 唯一键复用完成结果，HTTP 前提交 dispatched，未知结果不自动重派；Actor Mapping 简介保持权威，AI 失败只形成 warning 且不改变 `core_ready`。
- TASK-010 自动验证覆盖 389 项自包含测试、PostgreSQL 并发与 Schema 聚焦、无剩余 P0/P1/P2 只读审计，以及 Compose Final 的 72 项 PostgreSQL/运行测试、迁移、五服务健康、重启恢复、秘密扫描和资源清理。
- TASK-011 已交付 core-ready 媒体库、同来源组合筛选、版本化键集游标、全局搜索与补全、影片/演员详情、单一收藏和受认证永久图片读取。
- 0011 启用 `pg_trgm` 并建立标题/姓名/别名 GIN、favorite 唯一事实；Phase 1 availability/progress 使用稳定空端口，搜索 queued 原子提升且 failed 不自动重试。
- TASK-011 自动验证覆盖 408 项自包含测试、289,858 来源/100,000 别名规模 p95 与 B-tree/GIN 计划、无剩余 P0/P1/P2 审计，以及 Compose Final 的 78 项 PostgreSQL/运行测试、迁移、健康、重启恢复、秘密扫描和资源清理。
- TASK-012 已交付 JavDB 日/周/月/TOP250 总榜与年度榜持久请求、01:45 调度、worker claim/heartbeat、不可变快照、snapshot-bound cursor、priority 20 元数据协调和受认证本地查询 API。
- 0012 以 current/active 部分唯一索引、owner/token/lease fencing 和短事务原子切换保证失败保留；晚到 Movie 按番号重新关联，TOP250 无凭据/失效/未同步/同步失败使用稳定 503 reason。
- TASK-012 自动验证覆盖 450 项自包含测试、PostgreSQL 迁移/并发与 250 条快照 p95、完整差异审计，以及 Compose Final 的 83 项 PostgreSQL/运行测试、迁移、健康、重启恢复、秘密扫描和资源清理。
- TASK-013 已交付全局 sequence/持久 stream version、30 天事件清理、事务元数据事件、鉴权 WebSocket、有界 REST snapshot、对象级 JavDB/AI clear/replace CAS、TTL/同步设置、typed 连接测试和严格诊断 DTO。
- 0013 新增事件水位、聚合版本、事件正文和连接测试结果；API/worker/metadata child 在同一领域事务写事件，scheduler 每日只清理过期正文，worker/scheduler 无心跳证据时诊断保持 unknown。
- TASK-013 自动验证覆盖 466 项自包含测试、PostgreSQL 迁移/并发/回滚/恢复、完整差异审计，以及 Compose Final 尝试 2 的 84 项 PostgreSQL/运行测试、迁移、健康、重启恢复、秘密扫描和资源清理。
- TASK-014 已交付真实 PostgreSQL/Alembic 与生产服务组合的 Phase 1 后端 E2E，覆盖认证、AVdb 六分类导入、首批元数据、core_ready、目录/搜索/排行榜、事件、诊断、来源幂等、故障隔离和手动 retry。
- E2E 外部访问只使用固定 fixture 与 MockTransport；API/worker/scheduler 真实进程、重启、ready 降级和资源清理由同一次 Compose Final 验证，未新增生产测试开关、Schema 或公开 API。
- TASK-014 自动验证覆盖 466 项自包含测试和 88 项 PostgreSQL integration/E2E；正式评审为 `passed`，最终无剩余 P0/P1/P2。
- TASK-015 已完成后端 Python 纯卫生清理，锁定 Ruff 0.16.0/mypy 2.3.0，并建立实际 OpenAPI、13 份迁移和 SQLAlchemy 状态约束的可复现等价门禁。
- TASK-015 清理前后基线逐项相等；除两个无用 import 和已验证的等价异常局部变量外无语义差异，历史迁移和产品契约未改动。
- TASK-015 Fast 为 469 项通过；Compose Final 首次尝试通过 466 项自包含和 88 项 PostgreSQL integration/E2E，健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部完成。
- TASK-101 已交付精确 Cloud115Port/frozen DTO、稳定错误、安全协议适配器、可编排 Fake、无网络 fixture 和显式真实 115 只读探针；只选择性适配固定 revision 的 downurl RSA/XOR，并完成 GPLv3 来源声明。
- Cloud115 适配器覆盖 QR 四步、Cookie snapshot、凭据三态、目录、离线分页、递归枚举、原画、HLS、小文件和受管删除；逐跳 HTTPS 主机校验、响应上限、逐操作错误映射与秘密脱敏已冻结，数据库 credential CAS 仍由 TASK-102 拥有。
- TASK-101 Focused 为 38 项通过，镜像 readiness 为 6 项通过，Fast 为 504 项通过；Compose Final 第二次尝试通过 504 项自包含和 88 项 PostgreSQL integration/E2E，迁移、健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部完成，默认测试未访问真实 115。
- TASK-102 已交付进程内有界 QR 会话、认证 binding API、加密 Cookie 单事务 CAS、整表单例 `cloud115_binding` 与顶层 `SakuraPlayer-Cache` 确定性根目录。
- Cookie 固定使用 `encrypted_setting.key=cloud115.cookie` 并以 setting version 为唯一版本真相；同账号重扫允许轮换，不同账号禁止覆盖，旧探活 snapshot 不覆盖重扫，移动/删除根只标记 `detached`。
- TASK-102 Fast 为 533 项通过，隔离 PostgreSQL 聚焦为 5 项通过；Compose Final 第三次尝试通过 533 项自包含和 92 项 PostgreSQL integration/E2E，迁移、健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部完成，默认测试未访问真实 115。
- TASK-103 已交付 CacheJob 状态机、持久容量类别、全局请求幂等事实、固定 2 个 running/10 个 queued、来源安全端口、受认证缓存 API 和 Catalog availability 适配器。
- 创建、复用、状态推进与解绑 guard 共享 PostgreSQL advisory transaction lock；同 key 终态重放、同来源活动任务复用、binding 解绑历史和随机任务目录均由 Schema 与并发测试固定。
- TASK-103 Fast 为 596 项通过，隔离 PostgreSQL 聚焦为 17 项通过；Compose Final 通过 596 项自包含和 94 项 PostgreSQL integration/E2E，迁移、健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部完成，默认测试未访问真实 115。
- TASK-104 已交付持久 `submit_started_at/submit_uncertain`、owner/token/lease claim fencing、
  `SKIP LOCKED` worker、单次离线提交与分页对账、远端取消、正常/瞬时退避和 60 秒
  disposition；worker 通过加密 Cookie CAS 作用域接入真实 Cloud115 适配器。
- 不确定提交保留 running 容量并禁止自动重提；取消与 mkdir/submit/poll 竞态由 claim 和
  确定性任务目录收敛，存在目录时只转 `cleaning`，证明式删除与事件通知仍分别归 TASK-107
  和 TASK-112。
- TASK-104 Fast 为 624 项通过；Compose Final 首次尝试通过 624 项自包含和 99 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-105 已交付有界递归文件扫描、确定性媒体候选/分段评分、四格式字幕匹配、
  `remote_media/remote_subtitle/cache_job_media_selection` 迁移、resolving worker、受认证选择 API
  和 Catalog 真实大小投影。
- 单候选或唯一高置信候选才自动 `ready`；歧义候选保持 `awaiting_selection`，只有完整候选组选择才原子
  进入 `ready`。目录归属前后复核、claim fencing、复合归属外键和 deferred ready-selection guard
  阻止过期 worker、取消竞态或跨任务媒体写回。
- TASK-105 Fast 为 640 项通过；Compose Final 第二次尝试通过 640 项自包含和 101 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-106 已交付固定 revision 证据驱动的确定性失败分类、Resources 非敏感来源引用、
  `SourceRejectionPort` 客户端、offline/resolver 接入，以及 claim-fenced CacheJob failed 与唯一
  `cache.job.failed.v1` 事件。
- 初始永久拒绝白名单只含离线提交端点固定 not-found errno 和远端文件 `blocked=true`；普通
  remote failed、HTTP 400/422、缺失 info_hash、通用 request errno、网络、限流、配额、凭据和
  submit uncertain 不清磁力。拒绝后/任务失败前崩溃由 claim expiry 和首次 reason 重读收敛。
- TASK-106 Fast 为 667 项通过；Compose Final 第二次尝试通过 667 项自包含和 102 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-107 已交付可配置滑动 TTL、20 个安全收敛容量、稳定 LRU、最小 playback session 与
  完整 lease Schema/服务、cleanup claim/attempt fencing、证明式远端删除和手动重试 API。
- materialized cache 首次时钟、设置变更、TTL 优先、cleaning 预计释放量和 cleanup_failed 容量
  语义已冻结；lease/cleanup 统一 CacheJob 锁顺序，root/task/account/parent/name 不符只 detached。
- TASK-107 Fast 为 694 项通过；Compose Final 第四次尝试通过 694 项自包含和 103 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-108 已交付 12 小时 HMAC 播放会话、Windows/HarmonyOS 固定 UA、完整有序媒体逐段
  session/lease/stream URL、无 Bearer 能力校验和 Cloud115 原画 `302 no-store` 入口。
- stream 能力绑定 owner/session epoch/mode/UA/expiry，要求活动租约与 ready 缓存归属；上游
  短链只存在于请求调用栈，不进入数据库、日志或视频代理响应路径。
- TASK-108 Fast 为 700 项通过；Compose Final 第四次尝试通过 700 项自包含和 104 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-109 已交付 original/compatibility 双模式会话、仅 original unavailable 自动回退、类型化
  HLS DTO 校验、最高 bandwidth 稳定选择和完整 HLS 错误映射。
- Cloud115 适配器继续独占 master 请求/解析和 capability URL 校验；播放层不重复解析 m3u8，
  master/选中 variant UA 由后端证明，客户端子请求和真实链路仍由后续任务负责。
- TASK-109 Fast 为 720 项通过；Compose Final 第二次尝试通过 720 项自包含和 105 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-110 已交付 manifest 外置字幕授权集合、客户端内嵌轨道枚举声明、四格式鉴权下载、
  双重 8 MiB 上限、实时远端归属证明和稳定客户端副本生命周期映射。
- 下载绑定 owner/epoch/session/cache/media，使用平台固定 UA、UUID 安全文件名和原样字节；
  logout 204、TASK-112 cache cleaned 和本地过期职责不重叠，后端不保存字幕正文或客户端路径。
- TASK-110 Fast 为 729 项通过；Compose Final 首次尝试通过 729 项自包含和 113 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-111 已交付影片级唯一进度、expected-version CAS、95%/严格剩余不足 120 秒完成规则、
  未知时长、manifest/Catalog 真实投影，以及 progress PUT 与播放心跳 API。
- 心跳在同一事务内组合进度、lease 和 CacheJob TTL；无进度续租合法，`playing=false` 可 flush 后
  结束 lease，冲突整体回滚。进度独立于 source/cache/media/subtitle，跨端和缓存清理后仍保留。
- TASK-111 Fast 为 759 项通过；Compose Final 首次尝试通过 759 项自包含和 115 项 PostgreSQL
  integration/E2E，迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部
  完成，默认测试未访问真实 115。
- TASK-112 已交付 cache/credential 事务事件、幂等通知与已读、REST snapshot/角标、真实设置与
  脱敏诊断、取消/清理 API，以及 worker 启动时最多 100 次的有界恢复。
- 0020 创建 notification 并持久化 failure stage/cleanup reason；客户端按字段浅合并 cache event，
  `submit_uncertain` 不自动重提，materialized/terminal 状态不倒退，ready 通知不自动播放。
- TASK-112 Fast 为 772 项通过、PostgreSQL 聚焦 31 项通过；Compose Final 首次尝试通过 771 项
  自包含和 115 项 PostgreSQL integration/E2E，迁移、五服务健康、认证、秘密扫描、重启恢复和
  隔离资源清理全部完成，默认测试未访问真实 115。
- TASK-113 已交付状态化 Fake Cloud115 和生产服务组合 E2E，覆盖扫码绑定、来源请求、2/10 容量、
  60 秒后端观察边界、媒体候选/连续分段、原画/HLS、字幕、跨 client 进度 CAS、证明式清理、
  worker 恢复、来源拒绝、凭据故障和 AC-132 隔离。
- TASK-113 Fast 为 776 项自包含与 38 项 PostgreSQL 相关测试通过；Compose Final 首次尝试通过
  776 项自包含和 125 项 PostgreSQL integration/E2E，五服务健康、重启、ready 降级恢复、秘密扫描
  和隔离资源清理全部完成，默认测试未访问真实 115、JavDB 写操作或付费 AI。
- TASK-114 已冻结 `eb280ab^..baf218b` 的 126 文件清理 manifest、57 文件 mypy 清单和
  Phase 2 等价基线；批准文件无可确认卫生债务，生产源码、迁移、NOTICE、协议 fixture 与
  `real115` 配置零差异。TASK-015 历史迁移门禁已改为验证 0001 至 0013 集合完整存在。
- TASK-114 Fast 为 783 项自包含和 41 项 Phase 2 PostgreSQL integration/E2E 通过；Compose
  Final 首次尝试通过 776 项自包含和 125 项 PostgreSQL integration/E2E，完整运行与清理门禁通过。
- TASK-201 已交付 Flutter 3.29.2/Dart 3.7.2 Windows-only debug 工程、Riverpod 组合根、
  手写 typed routes、可注入认证状态、登录/Shell/全屏播放器占位和浅/深/系统主题；播放器主题
  固定深色，未生成其他平台 runner，release/私有安装包继续归 TASK-212。
- TASK-201 静态分析和 7 项 Flutter 测试通过，Windows debug build 与 3 秒进程启动冒烟通过；
  GPLv3、第三方精确版本和 libmpv 构建来源已进入工程。
- TASK-202 已交付 Dio/严格 DTO、secure storage、UUID v4 客户端实例、single-flight refresh、
  服务端配置与 bootstrap/login、认证 WebSocket、版本化事件合并、REST snapshot 恢复、生命周期
  与通知投递端口；Windows 系统通知适配器继续归 TASK-209。
- TASK-202 Fast 为 32 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并生成
  `sakuraplayer_windows.exe`，实际构建使用的 BuildTools 2022 已补齐 ATL。
- TASK-203 已交付 Windows 三入口桌面 Shell、顶部全局搜索/缓存/设置入口、严格搜索 DTO、
  防抖与迟到响应隔离、core-ready 补全刷新、权威 snapshot 容量桥接和固定尺寸缓存角标。
- TASK-203 Fast 为 45 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并生成
  新的 `sakuraplayer_windows.exe`。
- TASK-204 已交付严格 Movies DTO/API、认证封面读取、六分类与四标签/来源/可播放/大小/收藏筛选、
  generation 隔离游标分页、局部追加重试、固定桌面网格和影片级进度/完成卡片。
- TASK-204 Fast 与 Final 为 63 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并
  生成新的 `sakuraplayer_windows.exe`，未访问真实 115、JavDB 写操作或付费 AI。
- TASK-205 已交付严格 Ranking DTO/API、四榜单与 TOP250 年份选择、generation 隔离分页、
  刷新/追加快照保留、类型化不可用动作、原始 rank 角标和认证封面 MovieCard 网格。
- TASK-205 Fast 与 Final 为 86 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并
  生成新的 `sakuraplayer_windows.exe`，未访问真实 115、JavDB 写操作或付费 AI。
- TASK-206 已交付严格 Actor DTO/API、姓名/别名搜索、收藏分页与同步、UUID typed route、响应式
  列表/详情/写真查看器、关联 MovieCard，以及独立匿名 GFriends 有界临时缓存和会话清理。
- TASK-206 Fast 与 Final 为 114 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并
  生成新的 `sakuraplayer_windows.exe`，默认测试未访问真实 GFriends、115、JavDB 写操作或付费 AI。
- TASK-207 已交付严格 MovieDetail/MovieSource DTO/API、UUID typed route、详情/收藏 generation、
  六状态来源选择与大小真相、响应式资料/剧照/来源布局，以及媒体库、排行榜、女优关联和搜索四类入口。
- TASK-207 Fast 与 Final 为 133 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并
  生成新的 `sakuraplayer_windows.exe`，默认测试未访问真实 115、JavDB 写操作或付费 AI。
- TASK-208 已交付 115 QR 内存会话与串行轮询、13 状态缓存管理、TTL 与 JavDB/AI 对象级 CAS、
  五类连接测试、脱敏诊断、元数据完整/富化重试，以及设置与诊断 typed route 和响应式布局。
- TASK-208 Focused 为 24 项、Fast 与 Final 为 148 项 Flutter 测试通过，静态分析零问题；Windows
  debug build 通过并生成新的 `sakuraplayer_windows.exe`，默认测试未访问真实 115、JavDB 写操作或付费 AI。
- TASK-209 已交付严格播放请求 DTO/gateway、幂等 header、服务端 deadline 与单调倒计时、全屏等待导航锁、确认取消、详情来源接线、ready/queued/reused 协调和 Windows 即时通知适配器。
- TASK-209 Final 为 168 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并生成新的 `sakuraplayer_windows.exe`，默认测试未访问真实 115、JavDB 写操作或付费 AI。
- TASK-210 已交付候选组完整有序选择、ready 显式播放、job/media typed route、严格 playback manifest 与同源 capability、固定 Windows UA、media_kit 原画/兼容双模式、过期单次重签、in-flight seek 合并和自定义深色控制栏。
- TASK-210 Final 为 181 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并生成新的 `sakuraplayer_windows.exe`，默认测试未访问真实 115、JavDB 写操作或付费 AI。
- TASK-211 已交付四格式私有字幕缓存、内嵌/外置字幕与音轨选择、倍速/全屏/进度控制、自动续播、15 秒心跳、暂停/退出/完成 flush、CAS 冲突收敛、三类字幕清理和页面即时进度刷新。
- TASK-211 Final 为 201 项 Flutter 测试通过，静态分析零问题；Windows debug build 通过并生成新的 `sakuraplayer_windows.exe`，默认测试未访问真实 115、JavDB 写操作或付费 AI。
- TASK-212 已交付 Windows release/private ZIP、当前用户安装/卸载、SHA-256 与可选 Authenticode、GPL/Windows 依赖/项目移植来源许可证包、默认离线统一测试和显式 real115 QR/播放 harness。
- TASK-212 Fast 为冻结 Python 3.10.16 后端 AC-129 清单 173 项、Flutter unit/widget 206 项和 Windows Fake integration 1 项通过；Final release build 与 34 文件内容/许可证/native/hash 扫描通过，真实 AC-130 未执行。
- TASK-213 已交付 Windows Fake 全用户旅程和真实 115 AC-130 门禁，修复 AVdb 现行资产名/manifest、QR confirmed、离线分页配额、nullable DTO、Cloud115 能力域和 Range seek 验收模型阻断。
- TASK-213 Windows Fast 为后端算法 180 项、Flutter unit/widget 209 项、Fake smoke 1 项和用户旅程 4 项通过；后端 Fast 787 项、PostgreSQL 125 项、Compose Final 第二次尝试完整通过。真实 115 扫码、离线、三次 Range 206、HLS、95% 进度、active lease 拒绝和 cleaned 清理通过；本轮 `.srt` / `.ass` 按操作者批准 Delta 显式跳过。
- TASK-215 已交付 scheduler 首次全量幂等排队、AVdb 已导入数量、诊断元数据聚合进度和 Windows 中文状态；元数据主视图只显示进度与当前最多 3 个刮削番号，不再请求或展示逐任务分页。
- TASK-215 后端 Fast 为 788 项、Windows 完整测试 211 项；Compose Final 第三次尝试通过 788 项自包含和 125 项 PostgreSQL integration/E2E，Windows Release 构建成功。Final 性能门禁保持原阈值，并在暂停同宿主正式高负载后通过。
- TASK-216 已把 JavDB 核心、排行榜与登录切换到签名 JSON API，注入 JavDB/DMM/GFriends/AI 真实只读 probe，补齐严格 host 配置、DMM 请求兼容和 Windows 中文错误。
- TASK-216 后端 Fast 为 807 项、Windows 完整测试 211 项；Compose Final 第二次尝试通过 807 项自包含和 125 项 PostgreSQL integration/E2E。正式 probe 中 JavDB/GFriends/AI available，DMM 如实 unavailable，`core_ready` 从 10 增长到 26。
- TASK-218 已交付搜索 pending MovieId 与受限详情、仅 AVdb 安全字段投影、收藏防御，以及持久元数据领取 pause/resume、诊断真相和 Windows 中文控制。
- TASK-218 后端 Fast 为 812 项、Windows 完整测试 215 项、隔离 PostgreSQL pause/claim 与 Schema guard 通过；Compose Final 第三次尝试通过 812 项自包含和 127 项 PostgreSQL integration/E2E，迁移、健康、认证、秘密扫描、重启、ready 降级恢复和资源清理全部完成。
- TASK-219 已交付三常驻服务 Compose Watch、Windows 默认 API 基址安全接线和实际热更新启动；开发命令固定 `sakuraplayer` 项目名以复用现有卷，正式 Compose 和 release 默认不变。
- TASK-219 后端 Fast 为 812 项、host Compose 9 项，Windows 完整测试 218 项且 analyze 零问题；Compose Final 通过 812 项自包含和 127 项 PostgreSQL integration/E2E，Windows release 构建成功。Compose Watch 与 Windows debug 会话当前保持运行。
- TASK-220 已交付生产默认 5 秒的认证初始化恢复、迟到代次隔离、中文本机错误和初始化期间地址编辑，并将 Windows DPAPI 安全存储迁入可终止后台 isolate；失败不清除既有地址、令牌、字幕或私有缓存。
- TASK-220 Windows Final 为 `flutter analyze` 零问题、完整 Flutter 测试 225 项、Fake 集成 4 项和 Release 构建通过；用户直接启动 Release 实测确认停止转圈且地址提交按钮可点击。
- TASK-221 已交付白名单 `return_movie_id` typed player query，详情立即/等待 ready 播放退出回同一影片，缓存或非法返回目标安全回缓存；详情连续布局固定为来源、简介、剧照。
- TASK-221 Windows Final 为 `flutter analyze` 零问题、完整 Flutter 测试 228 项、Fake 集成 4 项和 Release 构建通过；最新 Release 已直接启动供继续实际体验。
- TASK-217 已交付 provider/ranking 首次启动事务性幂等排队、既有失败事实保护和 Actor Mapping 当前空 blacklist 兼容；原周日 05:00 与每日 01:45 调度不变。
- TASK-217 修复后 Fast 为 821 项；Compose Final 尝试 2 通过 821 项自包含和 127 项 PostgreSQL integration/E2E。正式 Actor Mapping/GFriends 各有 1 个 current，GFriends 关联 839 个头像与 5,320 张剧照，四个 ranking 请求均 completed。
- TASK-222 已交付应用内播放导航栈返回、DMM 搜索到精确详情的两阶段简介解析和诊断失败计数，并显式恢复 230 个当前榜单 transient full retry 与 1,990 个 DMM-only 富化 retry；永久未找到、active、core-ready 和其他富化未重试。
- TASK-222 Fast 为后端 824 项与 Windows 228 项，Compose Final 首次通过 824 项自包含和 127 项 PostgreSQL integration/E2E；Windows Fake 集成 5 项、Release 与 34 文件包扫描通过。正式 daily/weekly/monthly 可见数分别达到 19/5/2，DMM available 且 15 部本轮 retry 影片已有简介，GFriends 首屏 24 位中 10 位投影头像并完成真实图片读取。
- TASK-223 已把 GFriends 持久证据 URL 规范化为 Windows 可消费的无 query URL，并隔离非法可选头像/写真；目录只投影带完整摘要且状态为 ready/retry_pending 的真实封面，安全占位返回 null。
- TASK-223 Fast 为后端 842 项与 Windows 228 项，Compose Final 首次通过 842 项自包含和 127 项 PostgreSQL integration/E2E；Windows Fake 集成 1 项、用户旅程 4 项、Release 与 34 文件包扫描通过。正式严格 DTO、1958 张已验证封面、2115 条无摘要占位和永久图片零缺失核验通过；翻译成功数仍为 0，稳定失败为 guardrail/upstream，未调用付费 AI。
- TASK-225 已交付 `sakuraplayer-zh-v2` 唯一输出结构、硅基流动 Qwen3.5 非思考 profile、按类型和输入增长的有界 `max_tokens`、finish reason 拒绝和脱敏失败子分类；旧 v1 付费事实不修改、不自动批量重试。
- TASK-225 Fast 为 Ruff、857 项自包含和宿主配置通过；Compose Final 一次通过 857 项自包含与 128 项 PostgreSQL integration/E2E。显式真实硅基流动合成文本门禁 744 ms 通过严格 schema/protected guard，未写业务翻译记录或修改刮削队列。
- TASK-226 已交付 Cloud115 离线状态/字段兼容归一化、2 秒确认反馈和 1 秒 cache worker 空闲等待；保留 90 秒 claim fencing，`submit_uncertain` 不自动重复提交，覆盖 `11c8de8b`/`394a1904` 类故障。
- TASK-226 Fast 为 Ruff、858 项自包含和宿主配置通过；Compose Final 一次通过 858 项自包含和 128 项 PostgreSQL integration/E2E，迁移、健康、认证、秘密扫描、重启、ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。
- TASK-227 已交付详情中文-only 简介投影、认证影片级重新刮削 API 和 Windows 详情操作；服务端固定 MovieId 对应番号、priority 10 与 full attempt，queued/running 安全复用，终态历史和旧翻译事实保持不可变。
- TASK-227 Fast 为 Ruff、864 项自包含、宿主配置、Windows analyze、233 项 Flutter 测试和 4 项 Fake 用户旅程通过；Compose Final 一次通过 864 项自包含和完整 PostgreSQL integration/E2E，Windows Release、迁移、健康、认证、秘密扫描、重启、ready 降级恢复和隔离资源清理全部完成。
- TASK-214 已完成 131 个 Windows 历史文件的固定 review，只移除 `composition_root.dart` 两处调试输出；固定 UA、路由、DTO、播放器、seek、依赖、runner 和真实 115 脱敏证据协议均保持不变。
- TASK-214 Fast 为 format 97 文件、analyze 零问题、233 项 Flutter 测试、4 项 Fake 用户旅程和 1 项原生 Fake smoke 通过；Final Release 与 34 文件私有包许可证/native/hash/debug-secret 扫描通过。
- TASK-317 已重构 README 首屏与新手路径，提供固定 `v1.0.0` 的 Linux Docker Compose、五 secret、网络边界、维护命令和 Windows ZIP 安装闭环，并明确当前不生成单文件 EXE/MSI 安装器。
- TASK-317 经用户明确批准不执行本地 Focused/Fast/Final 或完整 Compose；定向链接、Markdown、Bash/PowerShell、版本、Compose config、Secret 模式与差异检查通过，完成态提交 `991f541` 的远程 Verify `30802911998` 全绿。
- `v1.0.0` 已发布 GitHub Windows ZIP 与 SHA-256，并向公开 GHCR 和 Docker Hub 推送五个后端镜像标签；双仓库 `1.0.0` digest 一致，Windows 与双镜像 provenance 均验证通过。
- TASK-318 已交付 Linux/NAS 一键安装脚本、五个本机 secret 自动安全生成、固定 SemVer Docker 部署包和 Release attestation 汇总；新手部署不再需要手工生成 secret。
- TASK-318 经用户明确批准不执行 Focused/Fast/Final 或完整 Compose；定向 Ruff、Shell 语法和 30 项测试通过，实际发布包白名单/SHA-256/0755 与隔离真实 Compose config 通过，临时 secret 已清理。
- TASK-319 已交付固定 Inno Setup 6.4.2 的 Windows 当前用户单文件安装器 EXE；安装器从已验证 ZIP bundle 构建，保留 ZIP 发布物，并接入版本输出、Release 上传和 artifact attestation。
- TASK-319 定向验证包括发布契约测试 `12 passed`、PowerShell 语法、Flutter release bundle、Inno 编译、安装器内容/sidecar SHA-256、隔离静默安装与卸载；安装器哈希为 `69fba7e2d427e62f094dba7f0409ace2f243353431c3f93528460e1d8770ef8e`。用户明确批准不运行三层后端验证或完整 Compose。
- TASK-320 已交付 `install-latest.sh` 远程引导器：一条 `curl | bash` 命令自动解析最新 Release、下载并临时解压 Docker 发布包，再调用包内安装器；推荐路径不要求用户手动下载、解压或执行 SHA256，原有校验文件和本地安装器继续保留。
- TASK-320 定向部署测试为 Linux 容器 `33 passed`，Ruff 格式/检查、Bash 语法、Compose config、`git diff --check` 和 secret 扫描通过；全部 `tests/start` 的 5 个失败来自测试容器缺少 Docker CLI/PowerShell及既有 worker 超时，未作为本任务完成证据。
- TASK-321 已修复远程引导器把 `.env`、`secrets/` 和 bootstrap token 留在临时目录的问题：发布文件复制到当前目录后才运行安装器；已有 `.env` 保留，旧运行容器的 secret 可恢复且不完整时拒绝混用。首次交互运行从 `/dev/tty` 选择 IPv4 host/port，无 TTY 默认 `127.0.0.1:8000`。
- TASK-322 已确认 GitHub `v1.0.1` 旧归档缺少 `install-latest.sh`，并让当前引导器兼容该历史资产；新归档仍严格要求并复制完整发布文件。定向 Linux 测试为 `38 passed`。
- TASK-323 已修复首次 host/port 输入写回安装目录 `.env`、新 Compose 使用 `data/` bind mount、旧 named volume 复制迁移，以及旧数据库角色密码与宿主 PostgreSQL secret 不一致导致的迁移失败；密码修复命令显式使用 `.env` 的 PostgreSQL 角色和数据库，不再连接可能不存在的默认 `postgres` 角色。远程引导器 Docker 依赖改为按需调用，并修复 Bash SQL 输出与多目录创建语法。此前 Linux 安装器回归为 `18 passed`；最新角色连接修复按用户要求未执行测试，待飞牛 NAS 实测。
- TASK-324 已交付受认证 MGDB `full_reconcile` 手动请求、活动请求复用与终态审计保留、Windows“立即全量同步”按钮和中文反馈；保存来源与周期同步语义不变。Final 同时修复 PostgreSQL 初始化临时服务器误报健康、测试 bind 数据隔离和一次性 migrate 重启边界。
- TASK-325 已交付 Windows AI replace 后权威 GET 与重启配置恢复、只发送影片标题/简介的 `sakuraplayer-zh-v3` 本地 protected 占位协议、停止新建演员简介 AI 事实，以及官方 SemVer Docker 镜像原地升级；升级保留 `.env` 非镜像项、`secrets/`、`data/`、PostgreSQL 设置和已刮削数据。Fast 全绿；Final 唯一失败为既有 TASK-011 影片列表 p95 在主机高负载下为 613.8ms，用户明确接受该性能例外并要求不重跑。
- TASK-304 已交付 HarmonyOS 媒体库：六分类/四标签/来源/可播放/大小/收藏组合筛选、默认 `publish_date_desc`、游标分页按 movie ID 去重、422 `validation_failed` 游标失效恢复、`favorite=true` 收藏浏览、进度按钮（未播放/继续 N%/已看完）、LazyForEach movie ID 键控网格、mediaquery 横竖屏响应式列数，以及空/加载/失败/追加失败状态。
- TASK-304 模拟器实测 ohosTest 39/39 通过（含新增 LibraryStore 7 项 JsUnit 与 LibraryPage 2 项 UiTest）；debug/release HAP 构建与 `verify-app success` 签名校验通过；并行只读审计 P0/P1 已修复（favorite 变更即刷新、游标 422 恢复、@Reusable、旋转响应、INVALID/加载态通知、progress 解析降级）。审计 P2 记录：追加全量 reload 与 O(n²) 去重在 24/页规模可接受；UiTest 无法可靠触发 bindSheet 关闭手势，sheet 关闭由生产 onDismiss 覆盖。
- TASK-305 已交付 HarmonyOS 日/周/月/TOP250 排行榜：只读后端 `/api/v1/rankings` 本地不可变快照、四榜单 segmented 切换、TOP250 总榜 + 服务端 `available_years` 年份 Select、`synced_at` 本地快照时间、Refresh 下拉刷新、rank 角标 + MovieCard 复用、竖屏 2/横屏 3 列响应式网格，以及空/加载/失败/不可用/追加失败互不冒充的状态区；503 `ranking_snapshot_unavailable` 仅固定 reason 进入不可用态（credentials_*/never_synced/sync_failed 中文文案），未知 reason 或非 503 回落普通失败。
- TASK-305 状态机对齐 Windows 契约：切换 board 清 year 与旧 items/cursor、generation 竞态丢弃迟到响应、刷新在途保留现有内容且失败保留 items/cursor/synced_at、追加失败局部重试、刷新期间禁止追加避免旧 cursor 混叠、cursor `validation_failed` 同 generation 重载第一页一次、会话变化（detach）清空全部状态；客户端不自行过滤来源/core_ready，不触发上游同步。
  - TASK-305 模拟器实测 ohosTest 60/60 通过（含新增 RankingsStore 18 项 JsUnit 与 RankingsPage 3 项 UiTest）；debug/release HAP 构建与 `verify-app success` 签名校验通过；并行只读审计 P0×1（切榜清空 items）/P1×3（刷新期禁追加、503 校验、切榜失败提示）已修复并补负例测试。审计 P2 记录：year 2008..2200 硬编码与 Windows 端/查询参数一致；FAILED 透传后端 message 与 LibraryPage 既有模式一致；build 重计算（columnsTemplate/yearOptions/Date.parse）与 LibraryPage 同模式；Refresh 空态下拉立即收回可接受；updateColumns 与 mediaquery 双机制与 LibraryPage 同源；UiTest Fake/工具函数跨测试文件拷贝留待公共 test-utils。
- TASK-306 已交付 HarmonyOS 女优列表/详情/写真：姓名与权威别名搜索（300ms 防抖 + Enter 提交）、普通/收藏（`favorite=true`）分段模式、游标分页与 422 恢复、单一收藏（在途防重、成功同步列表与详情、favorite 模式取消收藏移除项、失败保留旧值）、详情（头像/中日文名不重复/别名/简介/写真/关联影片只读 MovieCard）、以及 GFriends 私有有界缓存。
- TASK-306 缓存：只信任后端唯一匹配 URL（逐字段白名单 + `%2e/%2f/%5c` 编码形态与解码后点段/反斜杠拒绝）、匿名下载（无 Authorization/Cookie，3 重定向逐跳校验、8 MiB、JPEG/PNG/WebP 签名 + Content-Type 精确匹配）、文件 LRU（cacheDir/gfriends-v1 + index.json，512 文件/256 MiB/7 天滑动，证明式清理）+ 内存 PixelMap LRU（64 张，ImageSource 按需解码）、single-flight + 4 并发、`EntryAbility.onMemoryLevel`（LOW/CRITICAL 收缩）、logout 证明式清空；图片生命周期与媒体库永久图片分离。
- TASK-306 模拟器实测 ohosTest 93/93 通过（含 Actors 13 项 JsUnit、GfriendsCache 14 项 JsUnit、UiTest 2 项）；debug/release HAP 构建与 `verify-app success` 签名校验通过。并行只读审计 P0×2（收藏在途切换 scope 污染新列表、scope 切换不清在途集合）/P1×7 已修复（URL 编码绕过、onMemoryLevel 释放正在渲染图、loadMore 失败自动重试、详情收藏 gen 守卫、列表→详情收藏同步、GfriendsImage 首屏加载、MovieDetail/PendingDetail 补 NavDestination）。审计 P2 记录：下载无流式截断（Network Kit ARRAY_BUFFER，8 MiB 兜底）、测试 sleep 轮询可选、mediaquery 与 updateColumns 列数口径与 LibraryPage 同源、appNavigationPathStack 模块级全局（配对正确低风险）、attach 一次性求值（实测 UiTest 时序成立）、favorite 移除后空态 nextCursor 非空（边缘 UX）。
- TASK-307 已交付 HarmonyOS 影片详情多来源与收藏：MovieDetail/MovieSource 严格 DTO（枚举/上限/去重/严格 UUID/source_count 正整数/metadata_error_code 仅 failed）、getMovie/setMovieFavorite（PUT/DELETE 204）、MovieDetailStore（generation 竞态、跨影片清空来源选择/同影片重载保留、收藏在途防重/失败保留/受限详情不收藏、ProtocolException→client_protocol_error）、MovieDetailPage（连续滚动单面：资料头/受限状态/来源/简介/剧照；openBindSheet 来源选择只产出 source_id、rejected 永久禁用；播放按钮未选来源禁用；进度文案与 MovieCard 同源）、SourceSheet（六状态与大小文案按 Windows 契约：ready→视频文件大小/其他→资源大小）、CatalogImage + core/images/CatalogImageCache（认证图片白名单 + 严格 UUID + 内存 LRU 64 + 退出登录清理 + 干净路径避免双 /api/v1 前缀）；媒体库/排行榜卡片补详情导航入口。模拟器实测 ohosTest 129/129 通过（新增 MovieDetail 19 项 JsUnit、SourceSheet 7 项、CatalogImage 4 项、UiTest 3 项）。并行只读审计 P1×3 已修复（跨影片切换不清来源选择、CatalogImage 双 /api/v1 前缀 404、logout 未清认证图片缓存）+ P2 修复（DTO 严格性、onSelect 以 store 回读、sheet dispose 时机、@Reusable 同 URL 重载）。审计 P2 记录：播放按钮未注入 sink 前选中即启用（播放由后续任务接续）、封面 130x195 为移动端 2:3 取舍（Windows 桌面 900px 阈值不移植）、未认证时详情空态无提示（路由仅认证态可达）。

## 1.1 当前任务门禁状态

- **当前任务门禁阶段**: TASK-325 completed；性能门禁例外已由用户明确接受，下一步定位 GFriends 女优资料链路。
- **最近绿色快速门禁**: 后端自包含 `927 passed, 11 deselected`；宿主 Docker 契约、scoped Ruff、Windows 237 项完整测试和 `flutter analyze` 均通过。
- **最终门禁状态**: 自包含 `931 passed, 11 deselected`；PostgreSQL integration/E2E 128 项通过，既有 TASK-011 影片列表 p95 613.8ms 未满足 500ms 门禁。用户明确接受该性能例外并要求不重跑；临时 Compose 资源已清理。
- **执行流程**: 采用 [统一实施与验证工作流](implementation-workflow.md)，先 Focused/Fast，再只读审计，最后 Final；不使用 Superpowers 插件或 `superpowers:*` 技能，复杂任务继续使用 `planning-with-files-zh`。

## 2. Git 状态基线

已完成的文档提交：

```text
2cf0b2c 文档：冻结 SakuraPlayer v1 需求规格
7480775 文档：确定 SakuraPlayer v1 技术架构与接口契约
fcf8bdf 文档：拆分 SakuraPlayer v1 实施任务与追踪矩阵
```

本交接文件、运行契约和接口补强属于其后的实施准备提交。新会话先运行 `git status --short` 和 `git log -5 --oneline`，不得假设工作区干净。

## 3. 恢复状态

- **已完成任务**: TASK-001、TASK-002、TASK-003、TASK-004、TASK-005、TASK-006、TASK-007、TASK-008、TASK-009、TASK-010、TASK-011、TASK-012、TASK-013、TASK-014、TASK-015、TASK-101、TASK-102、TASK-103、TASK-104、TASK-105、TASK-106、TASK-107、TASK-108、TASK-109、TASK-110、TASK-111、TASK-112、TASK-113、TASK-114、TASK-201、TASK-202、TASK-203、TASK-204、TASK-205、TASK-206、TASK-207、TASK-208、TASK-209、TASK-210、TASK-211、TASK-212、TASK-213、TASK-214、TASK-215、TASK-216、TASK-217、TASK-218、TASK-219、TASK-220、TASK-221、TASK-222、TASK-223、TASK-224、TASK-225、TASK-226、TASK-227、TASK-315、TASK-316、TASK-317、TASK-318、TASK-319、TASK-320、TASK-321、TASK-322、TASK-323、TASK-324、TASK-325、TASK-301、TASK-302、TASK-303、TASK-304、TASK-305、TASK-306、TASK-307。
- **下一任务**: TASK-326；定位并修复 GFriends 女优映射、头像、简介和写真链路。
- **当前阻塞项**: 无。Python 3.10.16、Ruff 0.16.0 和测试依赖由锁定 Docker test image 提供，不依赖宿主 Python。
- **未完成外部门禁**: TASK-317 首发外部门禁和 TASK-213/AC-130 Windows 真实 115 门禁已完成；HarmonyOS 不再设置 API 24 物理真机外部门禁。

TASK-318、TASK-319 与 TASK-320 已完成，`v1.0.0` 既有首发不追溯增加 Linux 部署包、Windows 安装器或远程引导资产；未来正式 tag 才生成新增发布资产。TASK-301 至 TASK-307 已完成（ohosTest 模拟器实测 129/129 通过）。Windows 客户端与普通后端 Compose 均已停止，持久卷保留。`.planning/` 只保存本地执行证据，不纳入 Git；提交、tag、Release 和 registry 摘要为最终事实。

## 4. 必读契约

| 开始内容 | 必读文件 |
|---|---|
| 工程与 Compose | `contracts/runtime-configuration.md`、`contracts/operational-health.md`、`architecture.md`、`TASK-001.md` |
| AVdb 导入 | `contracts/avdb-source.md`、`TASK-004.md` |
| REST/客户端 | `contracts/rest-api.openapi.yaml`、`contracts/error-codes.md` |
| 实时状态 | `contracts/realtime-events.md` |
| 元数据 | `contracts/metadata-providers.md` |
| 目录与发现 | `contracts/catalog-discovery-ports.md` |
| 115 与播放 | `contracts/cloud115-port.md` |
| 数据库 | `data-model.md` |

## 5. 本地原始资料

仓库根目录目前保留三份用户提供的未跟踪资料：

- `AVDB-DATABASE-GUIDE.md`
- `SakuraMedia-Windows-Android-播放与架构分析.md`
- `SakuraMedia-排行榜-女优-详情页分析.md`

它们是核验来源，不是实现契约。实现必须以 `docs/specs/` 中已提交的文档为准；不得在没有用户授权时把三份原始资料加入 Git。

## 6. 外部门禁

- TASK-213 真实 Windows、真实 115 和专属测试目录门禁已完成，专属验收 Compose 与远端任务目录已清理。
- TASK-317 首发已完成：`v1.0.0` 指向 `991f541`，Release `30803267055` attempt 2 全绿；GitHub Release 包含 `SakuraPlayer-Windows-1.0.0-1.zip` 与校验文件，GHCR 匿名拉取返回 200，GHCR/Docker Hub `1.0.0` digest 均为 `sha256:f328eef81f09739bae2dda16560dcedb2b5bbfbad2e4f28bbebf3fb59209ff0a`。
- TASK-312 已按 `2026-08-04--harmony-baseline-and-device-gate.md` 撤销，仅保留历史记录；当前鸿蒙基线为 DevEco Studio 6.1.1.290、OpenHarmony SDK API 24（包标记 6.1.1.125）、Hvigor 6.24.3、ohpm 6.1.2.285、DevEco 内置 Node 18.20.1。
- 外部凭据不进入仓库、普通日志、测试快照或聊天输出。
