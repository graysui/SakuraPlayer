# SakuraPlayer v1 需求追踪矩阵

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**任务总索引**: [2026-07-24--sakuraplayer-v1--tasks.md](2026-07-24--sakuraplayer-v1--tasks.md)

## 映射规则

- `[I]` 对应规格中的 `[IMP]`，只列实际产出该行为的实现任务；自动验证细节保留在各实现任务和工作流 E2E 中。
- `[S]` 对应 `[SEF]`，只由可观察结果所属的 E2E 检查点验证，不创建实现任务。
- `[E]` 对应 `[EXT]`，只由需要真实外部系统的显式 E2E 门禁验证，不进入默认自动测试。
- 普通实现任务的 `provides` 和 Definition of Done 定义其产出角色；客户端任务消费公开契约，E2E 任务的 `ac-mapping` 表示验证范围而非实现所有权。一个 AC 映射多个任务时，不代表每个任务重复实现完整行为。
- 清理任务不承担新需求，因此不映射 AC。
- AC-133 的 bootstrap secret 启动依赖与管理员创建后失去权限的生命周期由 [Bootstrap Secret 生命周期澄清](changes/2026-07-24--bootstrap-secret-lifecycle.md) 冻结；TASK-001 负责启动校验，TASK-002 负责永久关闭初始化行为。
- AC-133 的 `X-Bootstrap-Token` 只在尚未初始化时必填；管理员存在检查必须先于 header/secret 校验，详见 [Bootstrap Header 条件校验](changes/2026-07-24--conditional-bootstrap-header.md)。
- AC-011/AC-012 的 JWT claim、refresh 轮换/重放、client instance、logout 与 session epoch 语义由 [认证会话生命周期补强](changes/2026-07-24--authentication-session-lifecycle.md) 冻结，并由 TASK-002 实现。
- AC-002、AC-011、AC-012、AC-115 至 AC-117、AC-133、AC-135 的 Windows single-flight refresh、客户端实例持久化、快照未知聚合版本基线、通知端口所有权和地址切换清理由 [TASK-202 客户端基础确定性边界](changes/2026-07-29--task-202-client-foundation-boundaries.md) 冻结；TASK-209 已接入 Windows 系统通知适配器。
- AC-133 的 bootstrap token 熵、规范 Base64URL 编码和固定长度摘要比较由 [Bootstrap Token 熵与比较规范](changes/2026-07-24--bootstrap-token-entropy.md) 冻结。
- AC-127 的内部探针、容器健康检查与 Schema 门禁由 [运维健康与 Schema 门禁契约](contracts/operational-health.md) 冻结；TASK-001 负责基础门禁，TASK-013/TASK-112 负责后续任务恢复与诊断。
- 实施验证顺序与技能边界由 [统一实施与验证工作流](implementation-workflow.md) 统一管理；该流程禁用 Superpowers 插件及其技能，保留 `planning-with-files-zh`，只约束执行与证据，不新增或删除 AC 映射。
- AC-036 的跨上下文最小输入、初始真实证据白名单、可恢复拒绝顺序、原子清密文、幂等、
  导入 anti-join 与确定性失败事件所有权由
  [TASK-106 来源拒绝确定性边界](changes/2026-07-28--task-106-source-rejection-determinism.md)
  和 [SourceRejectionPort 契约](contracts/source-rejection-port.md) 冻结，并由 TASK-006 提供、
  TASK-106 调用；TASK-112 不重复发布 TASK-106 已持久化的确定性失败事件。
- AC-028/AC-030 的标准番号、FC2、保守拒绝和固定样本由 [影片番号规范化输入边界](changes/2026-07-25--movie-number-normalization.md) 冻结，并由 TASK-005 实现。
- AC-018 至 AC-021 的 AVdb 资产名与公开信封兼容由 [TASK-213 AVdb 资产名兼容边界](changes/2026-07-31--task-213-avdb-asset-name-compatibility.md) 和 [TASK-213 AVdb manifest 兼容边界](changes/2026-07-31--task-213-avdb-manifest-compatibility.md) 冻结；TASK-004 保持发现、摘要、解密和导入主责，TASK-213 只修复真实门禁发现的官方带连字符时间戳与严格 manifest 阻断并验证隔离 30D 导入。
- AC-105/AC-130 的真实原画能力域兼容由 [TASK-213 Cloud115 能力域兼容边界](changes/2026-07-31--task-213-cloud115-capability-host-compatibility.md) 与 [Cloud115Port 契约](contracts/cloud115-port.md) 冻结；TASK-213 只增加真实观察且批准参考实现已记录的 `*.115cdn.net` HTTPS 子域，并保持每个并发 stream 请求独立签发能力 URL，其他主机、完整能力 URL 持久化和日志输出继续拒绝。
- AC-130 的 TASK-213 本轮外置字幕真实证据由 [TASK-213 外置字幕真实证据豁免](changes/2026-08-01--task-213-external-subtitle-evidence-waiver.md) 冻结；只有显式 marker 可把 `.srt` / `.ass` 下载替换为 `subtitle_external_skipped state=operator_approved`，字幕产品契约、默认自动测试及后续真实设备 ASS 门禁不变。
- AC-105/AC-130 的真实 Range seek 证据由 [TASK-213 Range seek 证据串行化](changes/2026-08-01--task-213-range-seek-evidence-serialization.md) 冻结；Windows probe 按生产 `ThrottlingPlayer` 顺序验证三个偏移，每次独立请求 stream，后端并发请求独立签发和不缓存能力 URL 的自动回归继续保留。
- AC-026/AC-027 的 90 日历日边界、5000 截断、稳定排序和无上限历史候选由 [首批元数据范围边界与排序](changes/2026-07-25--initial-metadata-scope-ordering.md) 冻结，并由 TASK-005 输出、TASK-007 消费。
- TASK-007 的元数据队列表、活动 attempt 部分唯一约束和 claim expiry 由 [元数据队列 DoR 迁移归属修正](changes/2026-07-25--metadata-queue-dor-correction.md) 明确归属 TASK-007，不改变 AC-037 至 AC-043、AC-122 或任务依赖。
- AC-047/AC-048 的永久图片精确 HTTPS 主机、MIME、8 MiB、重定向、像素、完整解码和原子替换边界由 [TASK-008 永久图片安全边界](changes/2026-07-26--task-008-image-security-boundaries.md) 冻结，并由 TASK-008 实现。
- AC-046、AC-069 至 AC-073 的排行榜持久请求、01:45 调度、2008..当前年 TOP250、快照唯一性、snapshot cursor、MovieSummary 端口、priority 20 提升和稳定不可用 reason 由 [TASK-012 排行榜快照确定性与执行边界](changes/2026-07-26--task-012-ranking-snapshot-boundaries.md) 冻结，并由 TASK-012 实现。
- AC-046、AC-069 至 AC-073 的 Windows Ranking DTO 所有权、类型化不可用 details、board/year generation、刷新/追加保留、固定桌面几何和会话内选择由 [TASK-205 Windows 排行榜客户端边界](changes/2026-07-30--task-205-rankings-client-boundaries.md) 与 [Windows 排行榜客户端契约](contracts/windows-rankings-client.md) 冻结；TASK-205 已完成客户端实现，自动证据位于 `api_client_test.dart`、`rankings_controller_test.dart`、`rankings_page_test.dart` 和 `app_bootstrap_test.dart`。
- AC-115、AC-116、AC-119、AC-121、AC-127 至 AC-129 的全局事件水位、有界一致快照、对象级配置 CAS、Phase 1 空 cache/credential 端口、unknown 诊断和分工作流测试责任由 [TASK-013 事件、设置与诊断确定性边界](changes/2026-07-26--task-013-events-settings-diagnostics-boundaries.md) 冻结，并由 TASK-013 建立基础端口、TASK-112/101/212 后续扩展；TASK-224 只补齐 API 运行镜像的 WebSocket 协议实现，不改变事件契约。
- AC-115 至 AC-119、AC-121、AC-122、AC-127 的 cache/credential 事务事件、通知幂等与已读、
  字段浅合并、cleanup reason、普通失败、诊断和逐状态启动恢复由
  [TASK-112 缓存事件、通知与恢复确定性边界](changes/2026-07-28--task-112-cache-events-recovery-contract.md)
  冻结；TASK-112 已实现 0020 Schema、事务事件/通知、快照/角标、诊断、操作和有界恢复，自动证据位于
  `test_event_integration.py`、`test_events_snapshot.py`、`test_notifications.py`、`test_recovery.py` 和
  `test_cache_events_snapshot_api.py`；不发布 playback 心跳事件，worker/scheduler 无心跳证据时继续为 unknown。
- AC-049 至 AC-053 的固定 provider 地址、16/32 MiB 上限、XML/路径安全、周日 05:00 持久入队、独立 current 快照、唯一身份匹配和陈旧 GFriends 资产清理由 [TASK-009 提供方快照安全与重建边界](changes/2026-07-26--task-009-provider-snapshot-boundaries.md) 冻结，并由 TASK-009 实现。
- AC-054 至 AC-058 的加密配置快照、单字段 JSON、protected 规范化、owner 作用域幂等键和付费派发事实由 [TASK-010 翻译协议与付费幂等边界](changes/2026-07-26--task-010-translation-safety-boundaries.md) 冻结并由 TASK-010 实现；prompt v2、硅基流动 Qwen3.5 非思考 profile、动态输出上限、安全诊断和旧 v1 事实隔离由 [TASK-225 硅基流动 Qwen 翻译协议兼容](changes/2026-08-02--siliconflow-qwen-translation-compatibility.md) 冻结并由 TASK-225 实现。
- AC-040/041/055/057/074/122 的详情中文-only 简介、影片级 priority 10 完整重新刮削、活动 attempt 复用和旧翻译事实保护由 [TASK-227 影片详情中文简介与重新刮削](changes/2026-08-03--movie-detail-chinese-description-rescrape.md) 冻结并由 TASK-227 实现。
- AC-063 至 AC-068、AC-074 至 AC-078 的同来源筛选、稳定键集游标、Phase 1 空状态端口、搜索队列提升、收藏 Schema、安全 DTO 与集合上限由 [TASK-011 目录查询与补全确定性边界](changes/2026-07-26--task-011-catalog-query-boundaries.md) 冻结，并由 TASK-011 实现。
- AC-063、AC-064、AC-067、AC-068、AC-077 的 Windows DTO 所有权、认证封面、固定桌面几何、筛选 generation、游标恢复和追加失败语义由 [TASK-204 Windows 媒体库客户端边界](changes/2026-07-30--task-204-library-client-boundaries.md) 与 [Windows 媒体库客户端契约](contracts/windows-library-client.md) 冻结；TASK-204 已完成客户端实现，自动证据位于 `library_controller_test.dart`、`library_page_test.dart`、`search_controller_test.dart` 和 `app_bootstrap_test.dart`。
- AC-051 至 AC-053、AC-075 至 AC-077 的 Windows Actor DTO 所有权、查询/收藏 generation、typed route、GFriends 精确 URL、匿名下载、取消、四并发、7 天期限、512 文件/256 MiB LRU、会话清理隔离和固定桌面几何由 [TASK-206 Windows 女优客户端边界](changes/2026-07-30--task-206-actors-client-boundaries.md) 与 [Windows 女优客户端契约](contracts/windows-actors-client.md) 冻结；TASK-206 已完成客户端实现，自动证据位于 `actors_controller_test.dart`、`actor_pages_test.dart`、`gfriends_cache_test.dart`、`desktop_shell_test.dart`、`auth_controller_test.dart` 和 `app_bootstrap_test.dart`。
- AC-031、AC-033 至 AC-035、AC-068、AC-074、AC-077、AC-078 的 Windows MovieDetail DTO 所有权、认证图片、MovieId typed route、加载/收藏 generation、来源状态/大小、显式 source_id-only 选择与固定桌面几何由 [TASK-207 Windows 影片详情客户端边界](changes/2026-07-30--task-207-movie-detail-client-boundaries.md) 与 [Windows 影片详情客户端契约](contracts/windows-movie-detail-client.md) 冻结；TASK-207 已完成客户端实现，自动证据位于 `movie_detail_controller_test.dart`、`movie_detail_page_test.dart`、`library_page_test.dart`、`rankings_page_test.dart`、`actor_pages_test.dart`、`desktop_shell_test.dart` 和 `app_bootstrap_test.dart`；play-request 继续由 TASK-209 交付。
- AC-084 至 AC-091、AC-117 的 Windows play-request DTO/gateway、服务器 deadline + 单调倒计时、等待导航锁、取消/窗口关闭和即时通知适配器由 [TASK-209 Windows 播放请求、等待与通知边界](changes/2026-07-31--task-209-playback-wait-notification-boundaries.md)、[Windows 播放请求客户端契约](contracts/windows-play-request-client.md) 与 [ADR-004](../adr/ADR-004-windows-cache-notifications.md) 冻结；TASK-209 已完成客户端实现，自动证据位于 `api_client_test.dart`、`play_request_controller_test.dart`、`blocking_wait_page_test.dart`、`event_client_test.dart` 和 `app_bootstrap_test.dart`，真实通知/安装包验收继续归 TASK-212/213。
- AC-093、AC-099 至 AC-106、AC-114 的 Windows ready route、候选组选择、manifest 严格消费、同 origin capability、固定 media_kit UA、双模式、错误恢复、seek 合并和基础控制由 [TASK-210 Windows 播放器确定性边界](changes/2026-07-31--task-210-windows-player-boundaries.md) 与 [Windows 播放器客户端契约](contracts/windows-playback-client.md) 冻结；TASK-210 已完成基础播放器，TASK-211 已完成字幕/音轨/心跳与影片进度接入，自动证据位于 `playback_api_test.dart`、`player_controller_test.dart`、`progress_controller_test.dart`、`track_controller_test.dart`、`subtitle_cache_test.dart`、`throttling_player_test.dart`、`player_page_test.dart`、`cache_page_test.dart` 和 `app_bootstrap_test.dart`；TASK-213 保留真实 115 链路门禁。
- AC-028/AC-029 的搜索字段、键集游标、安全响应和原子手动关联由 [待识别查询与关联确定性](changes/2026-07-25--pending-identification-pagination.md) 冻结，并由 TASK-005 实现。
- TASK-014 只验证 TASK-001 至 TASK-013 已交付的 Phase 1 后端切片；真实 PostgreSQL、应用服务组合、fixture、600 秒/性能证据复用和 Final runner 边界由 [TASK-014 后端元数据 E2E 确定性边界](changes/2026-07-27--task-014-e2e-boundaries.md) 冻结。其 `ac-mapping` 是验证范围，不转移前序任务实现所有权，也不覆盖 115、客户端或外部门禁。自动证据位于 `test_catalog_metadata_e2e.py`、`test_avdb_idempotency_e2e.py` 和 `test_metadata_failure_isolation_e2e.py`，正式评审结论为 `passed`。
- TASK-113 只验证 TASK-101 至 TASK-112 已交付的 Phase 2 后端可观察切片和 AC-132 的新增播放观察点；状态化 Fake、生产服务组合、60 秒/自动播放客户端责任和四方证据边界由 [TASK-113 115 缓存播放后端 E2E 边界](changes/2026-07-29--task-113-backend-e2e-boundaries.md) 与 [115 缓存播放后端 E2E 契约](contracts/backend-cloud115-e2e.md) 冻结。其 `ac-mapping` 是代表性组合验证范围，不转移前序实现任务或后续客户端任务的 AC 所有权，也不替代 TASK-213 真实 115 门禁。自动证据位于 `test_cloud115_cache_playback_e2e.py`、`test_cache_capacity_wait_e2e.py`、`test_cache_cleanup_faults_e2e.py` 和 `test_playback_security_e2e.py`，正式审计无剩余 P0/P1/P2，Compose Final 通过。
- TASK-015 不新增或接管产品 AC；其清理清单、锁定静态工具和 OpenAPI/迁移/状态机等价门禁由 [TASK-015 清理范围与等价门禁](changes/2026-07-27--task-015-cleanup-gates.md) 冻结。行为回归继续归属 TASK-001 至 TASK-014 的既有 AC 与完整 Final。
- TASK-114 不新增或接管产品 AC；其固定 Git 区间、126 文件 manifest、57 文件 mypy
  清单和 Phase 2 等价门禁由 [TASK-114 清理范围与等价门禁](changes/2026-07-29--task-114-cleanup-gates.md)
  冻结。行为回归继续归属 TASK-101 至 TASK-113 的既有 AC 与完整 Final，真实 115
  发布门禁仍归 TASK-213。
- TASK-201 的依赖、debug/release 边界、Flutter 生成文件范围、手写 typed routes 和最小
  `AuthSessionState` 由 [TASK-201 Windows 脚手架实施边界](changes/2026-07-29--task-201-scaffold-boundaries.md)
  冻结。TASK-201 实现 Windows debug 脚手架、工程许可证、主题和应用内播放器路由；
  AC-008 的 Windows 私有安装包归 TASK-212，AC-059 的最终左侧导航归 TASK-203。
- AC-005、AC-008、AC-009、AC-128、AC-129 的 Windows release、私有 ZIP、当前用户安装/卸载、
  SHA-256/可选 Authenticode、GPL/Windows 依赖/项目移植来源 NOTICE、默认离线统一测试和显式
  real115 harness 由 TASK-212 完成；自动证据位于 `license_bundle_test.dart`、
  `tooling_contract_test.dart`、`fake_backend_flow_test.dart` 和 real115 默认 skip build，真实账号与
  AC-130 证据仍只归 TASK-213。
- AC-005、AC-018 至 AC-021、AC-059 至 AC-122、AC-128 至 AC-130、AC-132 至 AC-135 的 Windows
  Fake 全用户旅程、现行 AVdb 兼容阻断、真实 115 扫码/离线/原画/HLS/Range/进度/租约/清理和首次连接
  证据由 TASK-213 完成；本轮 `.srt` / `.ass` 只按批准 Delta 记录操作者跳过，默认字幕自动测试不变。
- AC-083 至 AC-085、AC-091 的 SourceSubmissionPort、独立请求幂等事实、持久容量类别、
  binding 解绑历史、CacheJob/媒体迁移归属和复数媒体选择由
  [TASK-103 缓存容量与幂等确定性边界](changes/2026-07-27--task-103-cache-capacity-idempotency.md)
  冻结；TASK-103 实现创建与容量，TASK-104/105 分别消费提交载荷和媒体 Schema。
- AC-084、AC-086 至 AC-091、AC-097 的提交派发事实、`submit_uncertain`、claim fencing、
  disposition 和取消/清理/通知职责由
  [TASK-104 离线执行与取消确定性边界](changes/2026-07-27--task-104-offline-execution-determinism.md)
  冻结；TASK-104 实现离线执行与远端取消，自动证据位于 `test_offline_worker.py`、
  `test_play_disposition.py` 和 `test_cache_job_migration.py`；TASK-107/112 分别完成安全清理和
  事件通知。
- AC-035、AC-092、AC-093、AC-108、AC-109 的有界递归、媒体/字幕白名单、分段、评分、
  保守自动选择、字幕匹配和真实大小投影由
  [TASK-105 媒体解析确定性边界](changes/2026-07-27--task-105-media-resolution-determinism.md)
  冻结；TASK-105 实现持久媒体候选、有序选择与 `awaiting_selection -> ready`，自动证据位于
  `test_media_selection.py`、`test_file_resolution.py`、`test_adapter_contract.py` 和
  `test_cache_api.py`。
- AC-107 至 AC-110、AC-114 的内嵌轨道责任、外置字幕授权集合、固定下载响应、实时远端归属
  和 logout/cache-cleaned/local-expiry 清理由
  [TASK-110 字幕下载与生命周期边界](changes/2026-07-28--task-110-subtitle-contract.md) 冻结；
  TASK-110 已实现后端 manifest/下载，自动证据位于 `test_signature.py`、
  `test_subtitle_options.py` 和 `test_subtitle_download.py`；TASK-112 发布 cache cleaned，
  TASK-211 已完成 Windows 私有缓存、轨道选择和三类清理，自动证据位于
  `subtitle_cache_test.dart`、`track_controller_test.dart` 和 `player_page_test.dart`；TASK-311 后续实现 HarmonyOS 客户端。
- AC-068、AC-111 至 AC-114 的影片级 0019 Schema、未知时长、完成边界、expected-version CAS、
  无进度心跳和 lease/TTL/progress 原子事务由
  [TASK-111 进度与心跳确定性边界](changes/2026-07-28--task-111-progress-heartbeat-contract.md)
  冻结；TASK-111 已实现后端状态、manifest、目录投影和心跳，自动证据位于
  `test_completion_rule.py`、`test_progress_service.py`、`test_heartbeat.py`、
  `test_progress_api.py` 和 `test_cross_client_progress.py`；TASK-211 已完成 Windows 自动续播、心跳、
  flush、CAS 收敛和即时页面刷新，自动证据位于 `progress_controller_test.dart`、
  `player_controller_test.dart`、`library_page_test.dart` 和 `movie_detail_page_test.dart`；TASK-311 后续实现 HarmonyOS 控制器。
- AC-094 至 AC-098 的 materialized cache 首次 TTL、设置变更、20 个安全收敛目标、稳定 LRU、
  playback lease 最小 Schema、清理 claim/attempt 和证明式删除恢复由
  [TASK-107 缓存生命周期确定性边界](changes/2026-07-28--task-107-cache-lifecycle-determinism.md)
  冻结；TASK-107 创建 lease 外键所需最小 playback session Schema，TASK-108 仍独占会话签名
  与播放 API，TASK-111 消费 lease 做心跳续期。
- AC-013、AC-016、AC-094、AC-118 至 AC-122 的 Windows QR 内存生命周期、13 状态缓存操作、
  设置对象级 CAS、秘密只写输入、脱敏诊断、元数据重试和响应式页面由
  [TASK-208 Windows 设置与缓存客户端边界](changes/2026-07-30--task-208-settings-cache-client-boundaries.md)
  冻结；TASK-208 已完成客户端实现，自动证据位于 `qr_settings_test.dart`、`cache_page_test.dart`
  和 `app_bootstrap_test.dart`，且未提前实现播放请求、等待页、播放器或系统通知。
- AC-099、AC-100、AC-102、AC-104、AC-105 的固定平台 UA、逐段播放能力、原画阶段边界、
  活动租约和无 Bearer stream 校验由
  [TASK-108 播放会话契约闭合](changes/2026-07-28--task-108-playback-session-contract.md)
  冻结；TASK-108 实现签名会话与 302 原画入口，自动证据位于 `test_signature.py` 和
  `test_original_redirect.py`，TASK-109/111 分别扩展 HLS compatibility 与播放进度心跳。
- AC-101、AC-103 的自动 fallback 白名单、HLS DTO 稳定选择、协议解析职责和 UA 跨任务责任由
  [TASK-109 HLS 回退确定性边界](changes/2026-07-28--task-109-hls-fallback-boundaries.md)
  冻结；TASK-109 实现后端 original/compatibility，TASK-210/310 实现客户端模式和 HLS 子请求，
  TASK-213/312 保留真实链路门禁；TASK-109 自动证据位于 `test_hls_resolver.py` 和
  `test_compatibility_redirect.py`。

## 逐条追踪

| 验收条件 | 类型 | 需求组 | 实现或 E2E 检查点 |
|---|---|---|---|
| `AC-001` | `[I]` | `REQ-001` | `TASK-002` |
| `AC-002` | `[I]` | `REQ-001` | `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-003` | `[S]` | `REQ-001` | `TASK-313` |
| `AC-004` | `[I]` | `REQ-001` | `TASK-002` |
| `AC-005` | `[I]` | `REQ-002` | `TASK-001`, `TASK-201`, `TASK-212` |
| `AC-006` | `[E]` | `REQ-002` | `TASK-312` |
| `AC-007` | `[I]` | `REQ-002` | `TASK-301` |
| `AC-008` | `[I]` | `REQ-002` | `TASK-001`, `TASK-212`, `TASK-301` |
| `AC-009` | `[I]` | `REQ-002` | `TASK-001`, `TASK-201`, `TASK-212`, `TASK-301` |
| `AC-010` | `[I]` | `REQ-003` | `TASK-002` |
| `AC-011` | `[I]` | `REQ-003` | `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-012` | `[I]` | `REQ-003` | `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-013` | `[I]` | `REQ-004` | `TASK-101`, `TASK-102`, `TASK-208`, `TASK-308` |
| `AC-014` | `[I]` | `REQ-004` | `TASK-003`, `TASK-102` |
| `AC-015` | `[I]` | `REQ-004` | `TASK-003`, `TASK-102` |
| `AC-016` | `[I]` | `REQ-004` | `TASK-101`, `TASK-102`, `TASK-208`, `TASK-308` |
| `AC-017` | `[I]` | `REQ-004` | `TASK-003`, `TASK-101` |
| `AC-018` | `[I]` | `REQ-005` | `TASK-004`, `TASK-213`, `TASK-315` |
| `AC-019` | `[I]` | `REQ-005` | `TASK-004`, `TASK-213`, `TASK-315` |
| `AC-020` | `[I]` | `REQ-005` | `TASK-004`, `TASK-005`, `TASK-213`, `TASK-215` |
| `AC-021` | `[I]` | `REQ-005` | `TASK-004`, `TASK-005`, `TASK-213`, `TASK-215` |
| `AC-022` | `[I]` | `REQ-005` | `TASK-004`, `TASK-005` |
| `AC-023` | `[S]` | `REQ-005` | `TASK-014` |
| `AC-024` | `[I]` | `REQ-005` | `TASK-004` |
| `AC-025` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-026` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-027` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-028` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-029` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-030` | `[I]` | `REQ-007` | `TASK-005` |
| `AC-031` | `[I]` | `REQ-007` | `TASK-006`, `TASK-207`, `TASK-307`, `TASK-315` |
| `AC-032` | `[I]` | `REQ-007` | `TASK-006` |
| `AC-033` | `[I]` | `REQ-007` | `TASK-006`, `TASK-207`, `TASK-307` |
| `AC-034` | `[I]` | `REQ-007` | `TASK-006`, `TASK-207`, `TASK-307` |
| `AC-035` | `[I]` | `REQ-007` | `TASK-006`, `TASK-105`, `TASK-207`, `TASK-307` |
| `AC-036` | `[I]` | `REQ-007` | `TASK-006`, `TASK-106` |
| `AC-037` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-038` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-039` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-040` | `[I]` | `REQ-008` | `TASK-007`, `TASK-222`, `TASK-227` |
| `AC-041` | `[I]` | `REQ-008` | `TASK-007`, `TASK-227` |
| `AC-042` | `[I]` | `REQ-008` | `TASK-007`, `TASK-008`, `TASK-216`, `TASK-223` |
| `AC-043` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-044` | `[I]` | `REQ-009` | `TASK-008`, `TASK-216` |
| `AC-045` | `[I]` | `REQ-009` | `TASK-008`, `TASK-216`, `TASK-222` |
| `AC-046` | `[I]` | `REQ-009` | `TASK-008`, `TASK-012`, `TASK-205`, `TASK-216`, `TASK-305` |
| `AC-047` | `[I]` | `REQ-009` | `TASK-008`, `TASK-223` |
| `AC-048` | `[I]` | `REQ-009` | `TASK-008`, `TASK-223` |
| `AC-049` | `[I]` | `REQ-010` | `TASK-009`, `TASK-217` |
| `AC-050` | `[I]` | `REQ-010` | `TASK-009` |
| `AC-051` | `[I]` | `REQ-010` | `TASK-009`, `TASK-206`, `TASK-222`, `TASK-223`, `TASK-306` |
| `AC-052` | `[I]` | `REQ-010` | `TASK-009`, `TASK-206`, `TASK-222`, `TASK-223`, `TASK-306` |
| `AC-053` | `[I]` | `REQ-010` | `TASK-009`, `TASK-206`, `TASK-306` |
| `AC-054` | `[I]` | `REQ-011` | `TASK-010`, `TASK-225` |
| `AC-055` | `[I]` | `REQ-011` | `TASK-010`, `TASK-225`, `TASK-227` |
| `AC-056` | `[I]` | `REQ-011` | `TASK-010`, `TASK-225` |
| `AC-057` | `[I]` | `REQ-011` | `TASK-010`, `TASK-225`, `TASK-227` |
| `AC-058` | `[S]` | `REQ-011` | `TASK-014`, `TASK-225` |
| `AC-059` | `[I]` | `REQ-012` | `TASK-203`, `TASK-303` |
| `AC-060` | `[I]` | `REQ-012` | `TASK-203`, `TASK-303` |
| `AC-061` | `[I]` | `REQ-012` | `TASK-203`, `TASK-303` |
| `AC-062` | `[I]` | `REQ-012` | `TASK-201`, `TASK-303` |
| `AC-063` | `[I]` | `REQ-013` | `TASK-011`, `TASK-204`, `TASK-223`, `TASK-304` |
| `AC-064` | `[I]` | `REQ-013` | `TASK-011`, `TASK-204`, `TASK-304` |
| `AC-065` | `[I]` | `REQ-013` | `TASK-011`, `TASK-203`, `TASK-303` |
| `AC-066` | `[I]` | `REQ-013` | `TASK-011`, `TASK-203`, `TASK-218`, `TASK-303` |
| `AC-067` | `[I]` | `REQ-013` | `TASK-011`, `TASK-204`, `TASK-218`, `TASK-304` |
| `AC-068` | `[I]` | `REQ-013` | `TASK-011`, `TASK-111`, `TASK-204`, `TASK-207`, `TASK-211`, `TASK-304`, `TASK-307`, `TASK-311` |
| `AC-069` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-217`, `TASK-222`, `TASK-223`, `TASK-305` |
| `AC-070` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-071` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-222`, `TASK-305` |
| `AC-072` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-222`, `TASK-305` |
| `AC-073` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-074` | `[I]` | `REQ-015` | `TASK-011`, `TASK-207`, `TASK-221`, `TASK-223`, `TASK-227`, `TASK-307` |
| `AC-075` | `[I]` | `REQ-015` | `TASK-011`, `TASK-206`, `TASK-223`, `TASK-306` |
| `AC-076` | `[I]` | `REQ-015` | `TASK-011`, `TASK-206`, `TASK-306` |
| `AC-077` | `[I]` | `REQ-015` | `TASK-011`, `TASK-204`, `TASK-206`, `TASK-207`, `TASK-304`, `TASK-306`, `TASK-307` |
| `AC-078` | `[I]` | `REQ-015` | `TASK-011`, `TASK-207`, `TASK-307` |
| `AC-079` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-080` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-081` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-082` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-083` | `[I]` | `REQ-017` | `TASK-103`, `TASK-315` |
| `AC-084` | `[I]` | `REQ-017` | `TASK-103`, `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-085` | `[I]` | `REQ-017` | `TASK-103`, `TASK-209`, `TASK-309` |
| `AC-086` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-087` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-088` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-089` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-090` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-091` | `[I]` | `REQ-017` | `TASK-103`, `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-092` | `[I]` | `REQ-018` | `TASK-105` |
| `AC-093` | `[I]` | `REQ-018` | `TASK-105`, `TASK-210` |
| `AC-094` | `[I]` | `REQ-018` | `TASK-107`, `TASK-208`, `TASK-308` |
| `AC-095` | `[I]` | `REQ-018` | `TASK-107` |
| `AC-096` | `[I]` | `REQ-018` | `TASK-107` |
| `AC-097` | `[I]` | `REQ-018` | `TASK-104`, `TASK-107` |
| `AC-098` | `[I]` | `REQ-018` | `TASK-107` |
| `AC-099` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-100` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-101` | `[I]` | `REQ-019` | `TASK-109`, `TASK-210`, `TASK-310` |
| `AC-102` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-103` | `[I]` | `REQ-019` | `TASK-109`, `TASK-210`, `TASK-310` |
| `AC-104` | `[I]` | `REQ-019` | `TASK-108`, `TASK-201`, `TASK-210`, `TASK-221`, `TASK-222`, `TASK-310` |
| `AC-105` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-106` | `[I]` | `REQ-019` | `TASK-210`, `TASK-310` |
| `AC-107` | `[I]` | `REQ-020` | `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-108` | `[I]` | `REQ-020` | `TASK-105`, `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-109` | `[I]` | `REQ-020` | `TASK-105`, `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-110` | `[I]` | `REQ-020` | `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-111` | `[I]` | `REQ-020` | `TASK-111`, `TASK-211`, `TASK-311` |
| `AC-112` | `[I]` | `REQ-020` | `TASK-111`, `TASK-211`, `TASK-311` |
| `AC-113` | `[I]` | `REQ-020` | `TASK-111`, `TASK-211`, `TASK-311` |
| `AC-114` | `[I]` | `REQ-020` | `TASK-110`, `TASK-111`, `TASK-210`, `TASK-211`, `TASK-310`, `TASK-311` |
| `AC-115` | `[I]` | `REQ-021` | `TASK-013`, `TASK-112`, `TASK-202`, `TASK-224`, `TASK-302` |
| `AC-116` | `[I]` | `REQ-021` | `TASK-013`, `TASK-112`, `TASK-202`, `TASK-224`, `TASK-302` |
| `AC-117` | `[I]` | `REQ-021` | `TASK-112`, `TASK-202`, `TASK-209`, `TASK-302`, `TASK-309` |
| `AC-118` | `[I]` | `REQ-021` | `TASK-112`, `TASK-203`, `TASK-208`, `TASK-303`, `TASK-308` |
| `AC-119` | `[I]` | `REQ-022` | `TASK-013`, `TASK-112`, `TASK-208`, `TASK-215`, `TASK-216`, `TASK-217`, `TASK-308`, `TASK-315` |
| `AC-120` | `[I]` | `REQ-022` | `TASK-003`, `TASK-013`, `TASK-208`, `TASK-308` |
| `AC-121` | `[I]` | `REQ-022` | `TASK-013`, `TASK-112`, `TASK-208`, `TASK-215`, `TASK-216`, `TASK-217`, `TASK-218`, `TASK-222`, `TASK-308` |
| `AC-122` | `[I]` | `REQ-022` | `TASK-007`, `TASK-013`, `TASK-112`, `TASK-208`, `TASK-215`, `TASK-218`, `TASK-222`, `TASK-227`, `TASK-308` |
| `AC-123` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-124` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-125` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-126` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-127` | `[I]` | `REQ-023` | `TASK-001`, `TASK-013`, `TASK-112` |
| `AC-128` | `[I]` | `REQ-024` | `TASK-003`, `TASK-013`, `TASK-101`, `TASK-212`, `TASK-216` |
| `AC-129` | `[I]` | `REQ-024` | `TASK-013`, `TASK-101`, `TASK-212` |
| `AC-130` | `[E]` | `REQ-024` | `TASK-213` |
| `AC-131` | `[E]` | `REQ-024` | `TASK-312` |
| `AC-132` | `[S]` | `REQ-024` | `TASK-014`, `TASK-113`, `TASK-213`, `TASK-313` |
| `AC-133` | `[I]` | `REQ-025` | `TASK-001`, `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-134` | `[I]` | `REQ-025` | `TASK-001`, `TASK-219` |
| `AC-135` | `[I]` | `REQ-025` | `TASK-202`, `TASK-219`, `TASK-220`, `TASK-302` |

TASK-101 的 AC-013/016/017/128/129 映射还受
[Cloud115 协议就绪边界](changes/2026-07-27--task-101-cloud115-readiness.md) 中
REQ-CHG-128 至 REQ-CHG-136 约束；它不新增 AC，也不改变任务总数。

TASK-219 的 AC-134/135 映射还受
[前后端开发期热更新](changes/2026-08-01--development-hot-reload.md) 中
REQ-CHG-245 至 REQ-CHG-249 约束；它不新增 AC，总任务数增至 62。

TASK-220 的 AC-135 映射还受
[Windows 启动初始化恢复](changes/2026-08-01--windows-startup-recovery.md) 中
REQ-CHG-250 至 REQ-CHG-256 约束；它不新增 AC，总任务数增至 63。

TASK-221 的 AC-074/104 映射还受
[Windows 播放返回与详情布局恢复](changes/2026-08-01--windows-playback-return-detail-layout.md) 中
REQ-CHG-257 至 REQ-CHG-260 约束；它不新增 AC，总任务数增至 64。

TASK-217 的 AC-049 映射还受
[Actor Mapping blacklist 结构兼容](changes/2026-08-01--actor-mapping-blacklist-compatibility.md) 中
REQ-CHG-261 至 REQ-CHG-263 约束；它不新增 AC 或任务，总任务数仍为 64。

TASK-222 的 AC-040/045/051/052/069/071/072/104/121/122 映射还受
[实际体验内容恢复](changes/2026-08-01--runtime-content-recovery.md) 中
REQ-CHG-264 至 REQ-CHG-270 约束；它不新增 AC，总任务数增至 65。

TASK-226 的 AC-084/086/087/088/089/090/091 映射还受
[115 离线确认及时性与协议兼容](changes/2026-08-03--task-226-cloud115-offline-confirmation.md) 中
REQ-CHG-271 至 REQ-CHG-275 约束；它不新增 AC，总任务数增至 69。

TASK-227 的 AC-040/041/055/057/074/122 映射还受
[影片详情中文简介与重新刮削](changes/2026-08-03--movie-detail-chinese-description-rescrape.md) 中
REQ-CHG-289 至 REQ-CHG-295 约束；它不新增 AC，总任务数增至 70。
