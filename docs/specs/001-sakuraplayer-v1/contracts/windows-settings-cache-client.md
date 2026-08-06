# Windows 设置与缓存客户端契约

**Status**: Accepted
**Date**: 2026-07-30
**Owner**: TASK-208

本契约固定 Windows 对既有 115 binding/QR、cache jobs、settings、connection tests、metadata jobs 与 diagnostics API 的消费、状态动作、失败恢复和桌面布局。后端状态机、对象级 CAS、事件快照和安全删除真相继续以 `rest-api.openapi.yaml`、TASK-013、TASK-102、TASK-107 与 TASK-112 变更规格为准。

## 1. API 与严格 DTO

- TASK-208 建立 settings/cache gateway，复用 TASK-202 的 `ApiClient`、`CacheJobDto`、`MetadataJobDto`、`Cloud115BindingDto` 和 snapshot state，不复制或放宽这些共享 DTO。
- 新增 DTO 严格读取 `QrSession`、`CacheCapacity/CacheJobPage`、`Settings`、`ConnectionTest`、`Diagnostics` 与 `MetadataQueueControl`。未知枚举、非法 UUID/时间、负数计数、越界 TTL、重复 ID/阶段、超过契约上限或秘密响应字段均视为 `client_protocol_error`。
- `ProviderState.status` 固定允许 `unknown/available/unavailable/credentials_invalid/not_configured`；`ConnectionTest.status` 固定允许 `available/unavailable/credentials_invalid/not_configured`。客户端不得把 `unavailable` 推断成凭据失效。
- 所有路径 ID 必须先通过 UUID 校验。缓存列表 status 使用单个逗号分隔查询值，页面按服务端 cursor 和顺序追加，不在客户端重排任务真相。

## 2. 115 QR 与绑定

- 设置页先读取 `/cloud115/binding`。`unbound/expired/detached` 提供扫码入口；`active` 显示脱敏账号与缓存根状态；`unavailable` 保留绑定并提供连接重试，不自动清除 Cookie 或要求重新扫码。
- 创建 QR 后只在 controller 内存保存 PNG bytes、会话 ID和过期时间。只接受有效 PNG base64；离开扫码流程、确认成功、过期、取消、认证变化或 controller dispose 时清空图片和会话状态，不写磁盘、偏好、日志或 Widget 文本。
- `waiting/scanned` 每 2 秒轮询一次，任一时刻最多一个 poll；`confirmed` 只触发一次 confirm。`expired/canceled`、`cloud115_qr_session_not_found` 显示重新扫码；`cloud115_unavailable/rate_limited/protocol_error` 停止自动轮询并保留非秘密状态，用户显式重试。
- `cloud115_credentials_expired` 明确显示“凭据已失效，请重新扫码”；`cloud115_unavailable` 显示“115 暂时不可用，请稍后重试”。二者不得共用文案或状态转换。
- 解绑是独立危险操作并二次确认；活动缓存导致的 409 保留绑定和页面数据。TASK-208 不显示 Cookie、二维码 token/uid/sign、根 CID 或账号内部键。

## 3. 缓存页与操作

- 缓存页每页 24 项，显示固定 running `2`、queued `10`、ready `20` 容量及服务端当前计数。snapshot 更新触发当前列表刷新；列表 API 仍是分页与完整任务字段真相。
- 13 个状态文案固定为：`queued=排队中`、`submitting=正在提交`、`offlining=离线中`、`submit_uncertain=提交待确认`、`resolving=解析文件`、`awaiting_selection=待选文件`、`ready=可播放`、`cancelling=正在取消`、`cleaning=正在清理`、`cleanup_failed=清理失败`、`failed=任务失败`、`cleaned=已清理`、`detached=已失联`。
- 取消只对 `queued/submitting/offlining/submit_uncertain/resolving` 显示，必须先弹出二次确认，再发送 `{confirmed:true}`；不得先发送 false 试探。重复点击在途时禁用，202 后以响应替换当前项。
- 清理只对 `awaiting_selection/ready/cleanup_failed` 显示。`cache_active_lease` 保留原任务并提示正在播放；`cache_ownership_mismatch` 显示已失联且不得建议删除其他目录；普通失败保留列表和重试动作。
- `cancelling/cleaning` 不提供重复操作；`failed/cleaned/detached` 只读。TASK-208 不实现媒体选择、播放请求、自动播放、速度/并发设置或磁力展示。

## 4. 设置、秘密与连接测试

- TTL 使用整数输入/步进控件，范围 `1..168` 小时，服务端默认 24。保存时只 PATCH `cache_ttl_hours`；成功使用响应真相，失败保留服务端确认前值和用户输入以便重试。
- `ready_cache_limit=20`、`metadata_concurrency=3`、`metadata_timeout_seconds=600` 只读显示，不提供修改控件。启动级主密钥、JWT、播放 HMAC 和 bootstrap secret 不出现在可编辑表单。
- JavDB/AI 使用对象级 replace/clear CAS。replace 必须提交响应中的 `version` 作为 `expected_version` 和完整非秘密字段加新输入的 password/API key；clear 使用当前正版本。AI replace/clear 成功后必须再执行一次权威 `GET /settings`，以持久化读取结果更新 controller；GET 失败时保留 PATCH 响应但显示稳定错误。`state_conflict` 后重新加载，不自动用旧输入覆盖新版本。
- MGDB 数据源使用对象级 replace/clear CAS。replace 提交响应中的 `mgdb.version` 和 `source_url`；source URL 只接受契约规定的 GitHub HTTPS 仓库地址。成功后回显规范化 URL，`state_conflict` 后重新加载。
- password/API key 控件初始为空，不用占位值伪装已保存秘密；响应、页面树、错误和测试快照只显示 `password_configured/api_key_configured`。提交完成或离开页面时清空输入 controller。
- 设置输入同步标识必须包含可回显的 configured、version、base URL、model、timeout、username 和 MGDB source 等当前值，不能只比较 version。页面重建、客户端重启、认证服务端切换或同版本内容变化后都以最新 GET 投影覆盖旧 controller 文本。
- MGDB 不是磁力输入框；页面不读取、显示或保存磁力内容。
- 连接测试目标固定为 `cloud115/javdb/dmm/gfriends/ai`，同一目标在途时禁用。响应只显示 status、稳定 error code、耗时和检查时间，不展示上游正文。DMM/GFriends/AI 专属错误码必须映射为中文；未知码统一显示“未知错误”，不得直接展示英文稳定码。
- 设置页显示 MGDB 30D 增量与全量同步的中文状态、已导入总数、最近成功与下次计划。同步区提供单个“立即全量同步”按钮，只调用 `POST /settings/mgdb-sync-requests`；未配置 MGDB 或请求在途时禁用，成功显示“全量同步请求已提交”并刷新 Settings，失败保留原状态。后端复用同模式 `queued/claimed` 活动请求；只有终态请求时保留其审计记录并创建新请求。保存来源不自动同步，不提供手动增量或任意模式。协议枚举保持 `never/running/succeeded/failed`，显示映射由 TASK-215 统一处理。

## 5. 诊断与元数据操作

- 诊断页严格显示 component status、队列计数、最近最多 100 条失败和最多 5 条连接测试；只展示稳定 stage/error code、elapsed、attempt 和时间。worker/scheduler 的 `unknown` 原样显示，不伪造健康。
- Windows 主诊断视图不再请求元数据任务分页，只消费 `metadata_progress`，显示总体进度、完成/总数、失败数量和最多 3 个当前 running 番号；不得展示元数据队列明细或逐条铺开全部番号。既有逐任务分页和 retry API 继续作为兼容管理接口保留。
- diagnostics `queues.metadata_paused` 是元数据领取控制真相。进度标题行显示单个控制按钮：paused 时为“开始刮削”，否则为“暂停刮削”；请求在途禁用，成功后刷新 diagnostics，失败保留原状态并显示中文错误。
- 控制只调用 `PUT /admin/metadata-queue` 并发送单一布尔 `paused`。客户端不得把 resume 解释为排队、重试或更改并发；不得新增元数据逐任务列表或 WebSocket 控制事件。
- 富化阶段固定为 `images/dmm/actor_map/gfriends/translation`，永不显示 `javdb_core`。默认不选择 `translation`；仅当服务端把它列入 `retryable_stages` 且管理员显式勾选时发送。提交空集合、重复阶段或客户端自行推导的阶段均禁止。
- `metadata_job_no_retryable_enrichment`、`metadata_job_already_active` 与普通失败保留任务状态并允许刷新。任何重试成功都只显示新 queued attempt，不改写旧 attempt。

## 6. 路由、状态与布局

- `/app/cache` 和 `/app/settings` 保持 Shell 内顶级路由；新增 `/app/settings/diagnostics`，归属设置入口并可返回设置页。认证服务端或会话变化时增加各 controller generation，清空 QR/秘密输入/分页并忽略旧响应。
- cache/settings 页面采用连续滚动或分页列表，不把页面区段嵌套成装饰卡。可用宽度 `<900px` 使用 `16px`、否则 `24px` 水平内边距，内容最大宽度 `1280px` 并左对齐。
- 宽设置页使用左侧分区导航和右侧内容，窄布局使用顶部 Tab；缓存容量使用固定三列摘要，窄宽度可换为单列但计数区域尺寸稳定。任务行最小高度 `96px`，长 error/stage/番号省略或换行，不覆盖操作区。
- 使用 Switch/Checkbox 表示二元选择、Stepper/整数输入表示 TTL、菜单表示 provider/阶段、图标按钮用于刷新/返回，危险操作必须确认且使用错误色。所有图标按钮有 tooltip，状态同时使用文字而不是只靠颜色。

## 7. 验证

- DTO/API：五组端点、13 个 cache 状态、Provider `not_configured`、集合/范围/重复、严格秘密响应、CAS payload、UUID 路径和 202/201/200/204 响应。
- Controller：QR 轮询串行/停止/释放、expired/unavailable 区分、generation、分页、snapshot 刷新、操作在途、TTL/CAS、AI replace 后权威 GET 与页面重建恢复、连接测试、完整/富化 retry。
- Widget/Route：宽窄布局、QR 内存图片、容量与任务动作、取消/解绑确认、active lease、只读常量、秘密不回显、同步/诊断中文状态、MGDB 手动全量同步禁用/在途/成功反馈、元数据聚合进度与当前番号、设置与诊断 route。
