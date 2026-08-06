# SakuraPlayer v1 功能需求规格

**规格 ID**: `001-sakuraplayer-v1`

**创建日期**: 2026-07-24

**状态**: Frozen
**产品范围**: Docker 后端、Windows 客户端、后续 HarmonyOS 手机客户端

## 1. 目的

SakuraPlayer 是一个单用户私有视频目录与播放工具。它将 AVdb 资源帖子规范化为影片目录，持久化 JavDB 等来源的元数据，在用户明确选择资源并点击播放后提交 115 离线任务，并通过短期签名入口把播放器重定向到 115/CDN。系统只管理 `SakuraPlayer-Cache` 专属目录，不建设永久 115 媒体库。

本规格定义产品行为和验收边界。技术实现以同目录技术方案为准，但任何实现不得静默改变本规格。

## 2. 验收分类

| 标记 | 含义 | 验证方式 |
|---|---|---|
| `[IMP]` | 需要代码或配置实现 | 单元测试、集成测试或客户端测试 |
| `[SEF]` | 由实现自然产生的可观察结果 | 端到端测试 |
| `[EXT]` | 必须依赖真实外部系统验证 | 受控人工或显式集成测试 |

## 3. 用户与平台

### REQ-001 单用户私有产品

系统必须面向一个管理员用户和一个 115 账号，不提供注册、多租户或家庭成员隔离。

- **AC-001 `[IMP]`**: 首次部署可创建唯一管理员账号，后续客户端使用账号密码登录。
- **AC-002 `[IMP]`**: 所有业务 API、WebSocket 和播放签发入口都要求有效身份凭据。
- **AC-003 `[SEF]`**: 同一管理员在 Windows 与 HarmonyOS 上看到一致的目录、收藏、任务和播放进度。
- **AC-004 `[IMP]`**: 产品不显示年龄确认页面。

### REQ-002 平台与交付顺序

- **AC-005 `[IMP]`**: 第一阶段交付 Docker 后端和 Windows 10/11 Flutter 客户端。
- **AC-006 `[EXT]`**: Windows 核心链路通过真实 115 验收后，才允许开始 HarmonyOS 客户端实施。
- **AC-007 `[IMP]`**: HarmonyOS 客户端以 HarmonyOS 6.1.1 Release、API 24、ArkTS/ArkUI 和原生 `AVPlayer` 为基线；冻结工具链为 DevEco Studio `6.1.1.290`、OpenHarmony SDK API `24`（本机包标记 `6.1.1.125`）、Hvigor `6.24.3`、ohpm `6.1.2.285` 和 DevEco 内置 Node `18.20.1`，详见 [HarmonyOS 工具链基线变更](changes/2026-08-04--harmony-baseline-and-device-gate.md)。
- **AC-008 `[IMP]`**: Windows 使用私有安装包，HarmonyOS 使用开发者签名侧载，不提供公开商店发布流程。
- **AC-009 `[IMP]`**: 项目采用 GPLv3，并保留复用代码的许可证与来源说明。

## 4. 身份、凭据与安全

### REQ-003 管理员认证

- **AC-010 `[IMP]`**: 管理员密码必须使用适合密码存储的单向算法保存，不得明文落库。
- **AC-011 `[IMP]`**: 客户端使用短期访问令牌和可撤销的刷新机制，不保存管理员明文密码。
- **AC-012 `[IMP]`**: 退出登录后，本机令牌和本地字幕缓存必须失效或删除。

### REQ-004 115 扫码与凭据保护

- **AC-013 `[IMP]`**: Windows 和 HarmonyOS 客户端可发起 115 扫码登录并展示扫码状态；内部协议边界遵循 [TASK-101 Cloud115 协议就绪变更](changes/2026-07-27--task-101-cloud115-readiness.md)，Windows 轮询、内存图片与恢复遵循 [TASK-208 Windows 设置与缓存客户端边界](changes/2026-07-30--task-208-settings-cache-client-boundaries.md)。
- **AC-014 `[IMP]`**: 115 Cookie 仅由后端持有，使用 Docker Secret 或环境变量提供的主密钥加密后写入 PostgreSQL。
- **AC-015 `[IMP]`**: Cookie 更新采用并发安全写回，重新扫码不得被旧请求覆盖。
- **AC-016 `[IMP]`**: Cookie 失效必须返回稳定错误码并提示重新扫码，不得伪装成普通播放失败；临时 unavailable 与协议错误保持独立语义，Windows 文案与状态恢复由 [Windows 设置与缓存客户端契约](contracts/windows-settings-cache-client.md) 冻结。
- **AC-017 `[IMP]`**: 普通日志、异常和诊断 API 不得输出 Cookie、完整磁力、AI 密钥、上游响应正文或完整签名播放 URL。

## 5. AVdb 导入与资源目录

### REQ-005 数据获取、解密与同步

- **AC-018 `[IMP]`**: 后端使用管理员配置的 MGDB GitHub Release 数据源，按 [TASK-213 AVdb 资产名兼容边界](changes/2026-07-31--task-213-avdb-asset-name-compatibility.md) 识别冻结的紧凑或带连字符时间戳资产名，按 [TASK-213 AVdb manifest 兼容边界](changes/2026-07-31--task-213-avdb-manifest-compatibility.md) 严格验证旧版或官方现行公开信封声明，并按文档规定的 PBKDF2-HMAC-SHA256 与 AES-256-GCM 流程下载和解密资源包；未配置时不发起网络请求。
- **AC-019 `[IMP]`**: 后端使用一个由管理员输入的 GitHub 数据源；切换来源时必须校验 Release 资产集合、大小和 SHA-256 后才能导入，不内置第三方主源或备用源。
- **AC-020 `[IMP]`**: 首次部署先幂等排入一次全量基线；基线事实建立后每天 03:00（Asia/Shanghai）幂等导入 30D 增量包。首次与周期边界由 [TASK-215 首次同步与聚合进度体验](changes/2026-08-01--task-215-runtime-progress-ux.md) 冻结。
- **AC-021 `[IMP]`**: 每周日 04:00（Asia/Shanghai）读取全量包做插入与更新对账；首次全量不得因 scheduler 重启重复排入。
- **AC-022 `[IMP]`**: 全量包中缺失的既有资源不得自动删除、失效或禁止提交。
- **AC-023 `[SEF]`**: 同一 Release 或同一资源重复执行不会产生重复记录。
- **AC-024 `[IMP]`**: 同步游标、Release 标识、资产摘要、开始时间、完成时间和失败原因必须持久化。

### REQ-006 目标分类与首次范围

- **AC-025 `[IMP]`**: 只导入亚洲有码、亚洲无码、中文字幕、4K原版、素人有码、FC2 六个目标分类的全部历史资源。
- **AC-026 `[IMP]`**: 首批元数据队列仅包含最近 90 天、最多 5000 个唯一番号。
- **AC-027 `[IMP]`**: 首批完成后，系统继续补齐全部历史数据，不设置队列总量上限。
- **AC-028 `[IMP]`**: 缺少番号或无法规范化的资源保留在“待识别”列表，不进入媒体库或自动元数据队列。
- **AC-029 `[IMP]`**: 后台允许管理员手动把待识别资源关联到影片。

### REQ-007 影片与多资源关系

- **AC-030 `[IMP]`**: 同一规范化番号只建立一条影片记录，保留原始番号和别名。
- **AC-031 `[IMP]`**: 每条 MGDB/AVdb 帖子按来源和帖子 ID 独立保存，并可与同一影片形成多资源关系；Windows 详情的来源顺序、选择与 TASK-209 交接由 [TASK-207 Windows 影片详情客户端边界](changes/2026-07-30--task-207-movie-detail-client-boundaries.md) 冻结。
- **AC-032 `[IMP]`**: 后台支持对错误合并执行手动拆分或合并。
- **AC-033 `[IMP]`**: 资源列表使用可叠加标签，不把中文字幕、无码破解、4K、有码设计为互斥分类。
- **AC-034 `[IMP]`**: `section=中文字幕` 可产生中文字幕标签；`category=无码破解` 或标题明确包含无码破解可产生破解标签；`section=4K原版` 可产生 4K 标签；只有明确字段或元数据证据可产生有码标签。
- **AC-035 `[IMP]`**: AVdb `size` 在离线前显示为“资源大小”；115 枚举文件后显示真实视频文件大小；Windows 状态与空值文案遵循 [Windows 影片详情客户端契约](contracts/windows-movie-detail-client.md)。
- **AC-036 `[IMP]`**: 115 明确返回资源失效、违规或无法离线时，删除活动资源并保存不含磁力内容的拒绝标记，后续同步不得重新导入该来源帖子。

## 6. 元数据、演员与翻译

### REQ-008 元数据刮削队列

- **AC-037 `[IMP]`**: 元数据任务和结果必须持久化，后端重启后可继续调度。
- **AC-038 `[IMP]`**: 固定同时执行 3 个影片元数据任务，不提供并发数配置。
- **AC-039 `[IMP]`**: 单个影片任务总执行时间超过 600 秒时必须被父进程强制终止并标记失败。
- **AC-040 `[IMP]`**: 600 秒超时或其他任务失败后不得自动重试，只能由管理员手动重试；当前榜单瞬时失败的显式运行恢复遵循 [实际体验内容恢复](changes/2026-08-01--runtime-content-recovery.md)，详情页影片级显式完整重刮遵循 [影片详情中文简介与重新刮削](changes/2026-08-03--movie-detail-chinese-description-rescrape.md)。
- **AC-041 `[IMP]`**: 队列优先级依次为后台手动重试和用户搜索、排行榜缺失影片、每日新增、首批 90 天、历史补齐；同优先级按发布日期从新到旧。详情页重新刮削的活动任务复用和 priority 10 事务语义由 [影片详情中文简介与重新刮削](changes/2026-08-03--movie-detail-chinese-description-rescrape.md) 冻结。
- **AC-042 `[IMP]`**: JavDB 核心影片资料和关系成功保存即视为可展示；DMM、图片、GFriends 和 AI 失败不得阻塞影片上线；真实 provider 运行链路遵循 [外部元数据服务运行可用性](changes/2026-08-01--provider-runtime-availability.md)，可选资产的客户端安全投影遵循 [真实目录响应兼容与可选元数据状态](changes/2026-08-02--catalog-response-compatibility.md)。
- **AC-043 `[IMP]`**: 任务必须记录当前阶段、开始时间、耗时、尝试次数和失败原因。

### REQ-009 元数据来源

- **AC-044 `[IMP]`**: JavDB 是影片、演员关系和排行榜的主来源；生产搜索、详情与榜单必须使用已验证的严格 JSON 防腐层，不得依赖已被上游拒绝的 HTML 页面。
- **AC-045 `[IMP]`**: DMM 仅补充影片简介，失败时保留 JavDB 核心资料；搜索到详情的精确解析与既有 warning 显式恢复遵循 [实际体验内容恢复](changes/2026-08-01--runtime-content-recovery.md)。
- **AC-046 `[IMP]`**: JavDB 用户名和密码是可选的加密配置；未配置时跳过需要登录的 TOP250，并以稳定的“榜单暂无快照”状态返回，不影响其他功能或既有榜单快照；配置后的连接测试必须执行只读登录并区分凭据无效与上游不可用。
- **AC-047 `[IMP]`**: 影片封面、剧照和其他媒体库图片下载到后端持久化卷并永久保留，不随 115 缓存删除。
- **AC-048 `[IMP]`**: 图片下载失败时使用后端安全占位并进入可重试补齐状态；安全占位不得作为客户端真实封面投影，详见 [真实目录响应兼容与可选元数据状态](changes/2026-08-02--catalog-response-compatibility.md)。

### REQ-010 演员映射与 GFriends

- **AC-049 `[IMP]`**: 后端每周刷新 `actor-mapping.xml` 和 GFriends `Filetree.json`，失败时继续使用最近一次成功缓存；首次部署没有任何持久快照事实时立即幂等排入一次初始刷新。
- **AC-050 `[IMP]`**: 演员映射保存中文名、日文名、权威别名和可用简介，不把用户搜索词写入别名。
- **AC-051 `[IMP]`**: GFriends 同时提供头像和写真图库，但只有唯一、明确的姓名或别名匹配才能关联；歧义匹配必须丢弃，Windows 客户端只消费后端关联结果和精确 URL 边界由 [TASK-206 Windows 女优客户端边界](changes/2026-07-30--task-206-actors-client-boundaries.md) 冻结；持久证据 URL 到客户端安全 URL 的规范化由 [真实目录响应兼容与可选元数据状态](changes/2026-08-02--catalog-response-compatibility.md) 冻结。
- **AC-052 `[IMP]`**: GFriends 只持久化索引和 URL，图片按需进入客户端缓存，不镜像全部图片；Windows 下载并发、取消、大小和文件缓存遵循 [Windows 女优客户端契约](contracts/windows-actors-client.md)。
- **AC-053 `[IMP]`**: 媒体库永久图片与 GFriends 临时图片必须使用不同生命周期；Windows 目录、期限、LRU 和认证会话清理由 [Windows 女优客户端契约](contracts/windows-actors-client.md) 约束。

### REQ-011 AI 翻译

- **AC-054 `[IMP]`**: 后端支持 OpenAI 兼容接口，可原子配置 `base_url`、加密 `api_key`、`model` 和超时；缺失或非法配置不得访问 provider。硅基流动 Qwen3.5 的非思考 profile 与通用 provider 兼容边界由 [硅基流动 Qwen 翻译协议兼容](changes/2026-08-02--siliconflow-qwen-translation-compatibility.md) 冻结。
- **AC-055 `[IMP]`**: AI 在元数据可选阶段只异步翻译影片标题和影片简介，不翻译演员简介；历史演员 AI 译文保留，Actor Mapping 继续提供可用中文简介。影片详情简介只展示完成的中文译文，不回退或并列显示原文，详见 [影片详情中文简介与重新刮削](changes/2026-08-03--movie-detail-chinese-description-rescrape.md) 和 [TASK-325 AI 配置恢复、翻译瘦身与 Docker 原地升级](changes/2026-08-06--task-325-ai-settings-translation-docker-upgrade.md)。
- **AC-056 `[IMP]`**: AI 请求不得携带番号、演员姓名、厂商、系列或标签原值；这些值实际出现在当前标题或简介时由后端本地替换为无业务含义占位符，响应占位符缺失、增加、重复或改写时拒绝译文，通过后再本地恢复。
- **AC-057 `[IMP]`**: 原文、译文、来源内容摘要、模型、提示版本和付费派发事实必须持久化；同一 owner/source/model/prompt 业务键最多自动派发一次，来源未变化时不得自动重复付费翻译。完整协议和未知结果语义由 [TASK-010 翻译协议与付费幂等边界](changes/2026-07-26--task-010-translation-safety-boundaries.md) 冻结；prompt v2 与旧 v1 事实隔离由 [硅基流动 Qwen 翻译协议兼容](changes/2026-08-02--siliconflow-qwen-translation-compatibility.md) 冻结。
- **AC-058 `[SEF]`**: AI 不可用时，已完成核心元数据的影片仍可浏览和播放。

## 7. 发现、浏览与资料页

### REQ-012 主导航与主题

- **AC-059 `[IMP]`**: Windows 使用左侧导航栏，HarmonyOS 手机使用底部导航栏。
- **AC-060 `[IMP]`**: 两端主入口均为媒体库、排行榜、女优。
- **AC-061 `[IMP]`**: 顶部提供全局搜索、缓存状态入口和管理员设置入口。
- **AC-062 `[IMP]`**: 应用支持浅色与深色主题并默认跟随系统；播放器固定使用深色背景。

### REQ-013 媒体库与搜索

- **AC-063 `[IMP]`**: 媒体库使用一个去重影片网格，六个 AVdb 分类作为可组合筛选条件；多来源筛选必须按同一来源闭合，完整服务端语义由 [TASK-011 目录查询与补全确定性边界](changes/2026-07-26--task-011-catalog-query-boundaries.md) 冻结，Windows 客户端消费边界由 [TASK-204 Windows 媒体库客户端边界](changes/2026-07-30--task-204-library-client-boundaries.md) 冻结。
- **AC-064 `[IMP]`**: 默认按满足筛选的 AVdb 来源最新发布日期从新到旧稳定排序，并支持字幕、破解、4K、有码、来源、可播放状态和资源大小筛选；游标绑定完整筛选与排序，Windows 布局与分页恢复遵循 [Windows 媒体库客户端契约](contracts/windows-library-client.md)。
- **AC-065 `[IMP]`**: 全局搜索支持番号、影片标题、演员姓名和别名，结果按影片与女优分组；番号精确结果优先，歧义别名返回全部演员结果。
- **AC-066 `[IMP]`**: 搜索命中尚未刮削的 AVdb 番号时显示补全状态与稳定 MovieId；无任务时创建最高优先级任务，既有 queued 任务原子提升，running 复用，failed 不自动重试；queued/running/failed 占位均可进入明确的受限待补全详情。
- **AC-067 `[IMP]`**: 只有核心元数据成功的影片可以显示正式影片卡片和正式详情页；存在 active 来源的非 core-ready 影片只允许从补全占位进入受限详情，不得进入媒体库、排行榜或演员关联影片。
- **AC-068 `[IMP]`**: 影片卡片和详情页播放按钮显示影片级播放进度或已看完状态；TASK-111 交付前通过稳定只读端口返回 null，Windows 未知时长显示遵循 [Windows 媒体库客户端契约](contracts/windows-library-client.md)，详情来源选择与固定操作几何遵循 [Windows 影片详情客户端契约](contracts/windows-movie-detail-client.md)。

### REQ-014 排行榜

- **AC-069 `[IMP]`**: 排行榜使用 JavDB 本地不可变快照，不在页面打开时实时抓取；同步由 scheduler 持久入队、worker 执行；首次部署没有任何排行榜持久事实时立即幂等排入一次当前目标，Windows 页面消费与恢复边界由 [TASK-205 Windows 排行榜客户端边界](changes/2026-07-30--task-205-rankings-client-boundaries.md) 冻结。
- **AC-070 `[IMP]`**: 页面支持日榜、周榜、月榜、TOP250，以及 TOP250 总榜和 2008 至当前年的年度筛选；完整参数与调度边界由 [TASK-012 排行榜快照确定性与执行边界](changes/2026-07-26--task-012-ranking-snapshot-boundaries.md) 冻结，Windows 选择、分页与布局遵循 [Windows 排行榜客户端契约](contracts/windows-rankings-client.md)。
- **AC-071 `[IMP]`**: 榜单只展示存在 AVdb 资源且核心元数据已完成的影片。
- **AC-072 `[IMP]`**: 榜单命中“有 AVdb 资源但元数据未完成”的影片时，幂等创建或提升为 priority 20，running 复用且 failed 不自动重试；修复 provider 后的 transient failed 仍只允许管理员按 [实际体验内容恢复](changes/2026-08-01--runtime-content-recovery.md) 显式恢复。
- **AC-073 `[IMP]`**: 榜单同步失败、空响应或全无效响应时保留最近一次成功快照，不清空现有榜单；从未成功时返回结构化稳定不可用状态，Windows 错误动作与刷新保留语义由 [Windows 排行榜客户端契约](contracts/windows-rankings-client.md) 约束。

### REQ-015 影片详情与女优详情

- **AC-074 `[IMP]`**: 影片详情展示封面、中日文标题、番号、日期、厂商、系列、导演、演员、标签、评分、简介、剧照、观看进度、收藏和多来源资源；Windows DTO、route、失败恢复、认证图片与布局由 [TASK-207 Windows 影片详情客户端边界](changes/2026-07-30--task-207-movie-detail-client-boundaries.md) 冻结，中文简介与重新刮削动作由 [影片详情中文简介与重新刮削](changes/2026-08-03--movie-detail-chinese-description-rescrape.md) 冻结。
- **AC-075 `[IMP]`**: 女优列表支持姓名和别名搜索；Windows 查询 generation、分页恢复与路由遵循 [Windows 女优客户端契约](contracts/windows-actors-client.md)。
- **AC-076 `[IMP]`**: 女优详情展示头像、中日文名、别名、简介、写真图库、关联影片网格和收藏状态；所有嵌套集合使用确定性顺序且最多 100 项，Windows 写真失败隔离、查看器和布局由 [TASK-206 Windows 女优客户端边界](changes/2026-07-30--task-206-actors-client-boundaries.md) 冻结。
- **AC-077 `[IMP]`**: 首版提供可稳定游标分页查看的影片和女优单一收藏集合，不提供多个自定义播放列表；Windows 影片收藏筛选由 [TASK-204 Windows 媒体库客户端边界](changes/2026-07-30--task-204-library-client-boundaries.md) 约束，影片详情收藏恢复由 [Windows 影片详情客户端契约](contracts/windows-movie-detail-client.md) 约束，女优收藏与失败保留由 [Windows 女优客户端契约](contracts/windows-actors-client.md) 约束。
- **AC-078 `[IMP]`**: 首版不提供独立观看历史列表，即使后端持久化播放进度。

## 8. 115 离线与缓存

### REQ-016 专属缓存根目录

- **AC-079 `[IMP]`**: 首次绑定 115 时自动创建或确认 `SakuraPlayer-Cache` 根目录。
- **AC-080 `[IMP]`**: 每个离线任务使用根目录下的独立子目录，并记录账号、根 CID、任务目录 CID 和资源归属。
- **AC-081 `[IMP]`**: 系统只能管理有数据库任务记录且父目录为专属根目录的文件；不得扫描、移动或删除其他 115 内容。
- **AC-082 `[IMP]`**: 用户手动移动或删除缓存后，系统只标记本地记录失效，不追踪或模糊删除移动后的文件。

### REQ-017 用户触发与离线队列

- **AC-083 `[IMP]`**: 首版资源候选只来自管理员配置的 MGDB/AVdb 数据源，不查询其他磁力源，也不提供手动磁力输入；磁力仅在后端加密保存。
- **AC-084 `[IMP]`**: 只有用户在详情页选择具体资源并点击播放后才能创建离线任务；不得后台预取。Windows 请求、幂等键和 source_id-only 交接遵循 [Windows 播放请求客户端契约](contracts/windows-play-request-client.md)。
- **AC-085 `[IMP]`**: 同时运行的 115 离线任务固定最多 2 个，排队任务固定最多 10 个。
- **AC-086 `[IMP]`**: 有运行名额时进入全屏等待页，除二次确认的取消操作外禁止其他页面操作；Windows route 锁定和窗口关闭语义遵循 [Windows 播放请求客户端契约](contracts/windows-play-request-client.md)。
- **AC-087 `[IMP]`**: 立即执行的任务全屏等待总时长最多 60 秒；60 秒内完成则自动进入播放器。客户端以服务端 `wait_deadline` 初始化并用单调时钟倒计时。
- **AC-088 `[IMP]`**: 60 秒内未完成时退出等待并提示切换资源，原任务继续在 115 后台执行，不视为失败；deadline 后 ready 不自动播放。
- **AC-089 `[IMP]`**: 没有运行名额的任务进入队列后立即退出等待；开始执行或完成时通知，但不得自动播放。
- **AC-090 `[IMP]`**: 超时退出的任务稍后完成时保留为已缓存资源并通知用户，不得打断当前页面或播放。
- **AC-091 `[IMP]`**: 同一资源的重复点击必须复用已有排队、运行或就绪任务；客户端请求和后端 idempotency key 语义遵循 [Windows 播放请求客户端契约](contracts/windows-play-request-client.md)。

### REQ-018 文件解析与缓存生命周期

- AC-094 至 AC-098 的 materialized cache、TTL 初始化、20 个收敛目标、稳定 LRU、最小租约
  Schema、claim fencing 和证明式删除恢复由
  [TASK-107 缓存生命周期确定性边界](changes/2026-07-28--task-107-cache-lifecycle-determinism.md)
  冻结。
- **AC-092 `[IMP]`**: 离线完成后递归枚举视频和字幕文件，排除明显广告、样片和低于技术方案阈值的文件。
- **AC-093 `[IMP]`**: 能明确识别主视频时自动选中；存在多个有效候选时显示文件选择器；连续分段按顺序组成播放队列。Windows 候选组选择、ready 播放入口与显式播放交接遵循 [Windows 播放器客户端契约](contracts/windows-playback-client.md)。
- **AC-094 `[IMP]`**: 已物化的待选择/就绪缓存采用默认 24 小时滑动 TTL，可由管理员设置为 1 小时至 7 天；设置变更作用于新缓存和下一次成功访问，Windows 输入和失败恢复遵循 [Windows 设置与缓存客户端契约](contracts/windows-settings-cache-client.md)。
- **AC-095 `[IMP]`**: 就绪容量默认收敛到最多 20 个，超过目标时按稳定的最后访问顺序清理最久未访问且可清理的缓存；删除未确认或失败时不得虚减容量。
- **AC-096 `[IMP]`**: 正在播放的缓存拥有租约，租约有效时不得自动清理。
- **AC-097 `[IMP]`**: 运行中的任务不参与 TTL 或 LRU 清理，只能由用户取消。
- **AC-098 `[IMP]`**: 只有确认 115 任务目录删除成功或明确不存在后，缓存才可标记为已清理；清理失败必须可观察和重试，归属不符必须 detached 且不得删除。

## 9. 播放、字幕与进度

### REQ-019 安全直链播放

- AC-101/103 的自动回退白名单、HLS DTO 选择、协议/播放层职责和 UA 跨任务责任由
  [TASK-109 HLS 回退确定性边界](changes/2026-07-28--task-109-hls-fallback-boundaries.md)
  冻结。
- Windows 的 ready route、候选选择、manifest、固定 UA、模式、错误恢复和 seek 合并由
  [TASK-210 Windows 播放器确定性边界](changes/2026-07-31--task-210-windows-player-boundaries.md)
  与 [Windows 播放器客户端契约](contracts/windows-playback-client.md) 冻结。
- **AC-099 `[IMP]`**: 后端按媒体生成 12 小时有效的 HMAC 签名播放 URL，每次点击播放重新签发。
- **AC-100 `[IMP]`**: Windows 和 HarmonyOS 使用各自固定的 SakuraPlayer User-Agent，后端获取 115 地址时必须使用播放器后续请求的同一 User-Agent。
- **AC-101 `[IMP]`**: 后端优先获取 115 原画直链；只有 `cloud115_original_unavailable` 可自动回退，或用户切换兼容播放时，才使用可用的最高码率 HLS。
- **AC-102 `[IMP]`**: 播放入口校验身份、签名、过期时间和缓存归属后返回 `302` 与 `Cache-Control: no-store`，不得代理视频字节。
- **AC-103 `[IMP]`**: 播放器菜单只提供“原画”和“兼容播放”，不展示全部 HLS 档位。
- **AC-104 `[IMP]`**: 首版只支持应用内播放器，不调用外部播放器；应用内播放返回实际来源页面的导航栈语义遵循 [实际体验内容恢复](changes/2026-08-01--runtime-content-recovery.md)。
- **AC-105 `[IMP]`**: Windows 播放器必须合并高频 seek，避免同一签名 URL 上出现不受控的并发 Range 请求。
- **AC-106 `[IMP]`**: 首版不生成时间轴预览缩略图。

### REQ-020 字幕与播放进度

- **AC-107 `[IMP]`**: 播放器识别视频内嵌字幕和音轨；后端 manifest 只声明由客户端播放器枚举，不伪造内嵌轨道。
- **AC-108 `[IMP]`**: 后端在 115 任务目录中识别 `.srt`、`.ass`、`.ssa`、`.vtt`，客户端把选择的字幕下载到应用私有缓存后加载；下载与实时归属边界由 [TASK-110 字幕下载与生命周期边界](changes/2026-07-28--task-110-subtitle-contract.md) 冻结。
- **AC-109 `[IMP]`**: 同名字幕优先，多个字幕允许用户切换；manifest 只发布当前已选媒体队列授权的字幕，字幕失败不得阻止视频播放。
- **AC-110 `[IMP]`**: 115 缓存清理、账号退出或 manifest 本地字幕期限到期时，按稳定 cache job/subtitle ID 删除对应本地字幕副本；事件责任由 TASK-110 变更规格冻结。
- **AC-111 `[IMP]`**: 播放进度关联影片而不是临时媒体，并在 Windows 与 HarmonyOS 之间共享；影片状态、expected-version CAS 与心跳事务由 [TASK-111 进度与心跳确定性边界](changes/2026-07-28--task-111-progress-heartbeat-contract.md) 冻结。
- **AC-112 `[IMP]`**: 有未完成进度时自动续播，不弹出“从头播放”选择框；完成状态的权威位置为 0。
- **AC-113 `[IMP]`**: 已知时长且非零位置播放达到 95% 或严格剩余不足 2 分钟时标记为已看完，下次从头播放；未知时长只保存位置。
- **AC-114 `[IMP]`**: 播放器提供字幕、音轨、倍速、全屏和标准进度控制。

## 10. 实时状态、设置与诊断

### REQ-021 实时状态与通知

- **AC-115 `[IMP]`**: 后端通过 WebSocket 推送离线、缓存、刮削和凭据状态变化；持久事件使用全局单调水位追赶，同时保留聚合级版本用于资源合并。
- **AC-116 `[IMP]`**: 客户端重连后必须通过有界且与事件水位一致的 REST 快照恢复任务状态，不依赖遗漏的事件；全局水位由 [TASK-013 事件、设置与诊断确定性边界](changes/2026-07-26--task-013-events-settings-diagnostics-boundaries.md) 冻结，cache 字段合并与恢复由 [TASK-112 缓存事件、通知与恢复确定性边界](changes/2026-07-28--task-112-cache-events-recovery-contract.md) 冻结。
- **AC-117 `[IMP]`**: 应用运行或处于系统后台时显示离线完成通知；完全退出后不常驻，下次启动补拉未读通知和任务快照，已展示通知可幂等标记已读。Windows 即时通知和点击导航遵循 [Windows 播放请求客户端契约](contracts/windows-play-request-client.md)。
- **AC-118 `[IMP]`**: 顶部缓存入口显示排队、运行和就绪数量角标；Windows 缓存页状态、容量和操作遵循 [TASK-208 Windows 设置与缓存客户端边界](changes/2026-07-30--task-208-settings-cache-client-boundaries.md)。

### REQ-022 管理员设置与诊断

- **AC-119 `[IMP]`**: 客户端设置页管理 115、JavDB、AI、MGDB 数据源、缓存期限、同步状态和连接测试；五个连接目标必须执行真实只读 probe，未配置、凭据无效与上游不可用不得混淆；同步状态同时显示持久统计中的已导入总数；JavDB/AI/MGDB 以对象级版本 CAS 更新，非敏感现值可回显，密码、Cookie、API key 与磁力只返回配置状态或不返回；AI replace 成功后和客户端重启时必须从权威 GET 恢复当前非秘密配置，Windows 表单和秘密生命周期由 [Windows 设置与缓存客户端契约](contracts/windows-settings-cache-client.md) 约束。
- **AC-120 `[IMP]`**: 主密钥等启动级机密只能由 Docker Secret 或环境变量提供，不得通过客户端修改。
- **AC-121 `[IMP]`**: 诊断页显示脱敏后的缓存失败、真实连接测试、元数据总体进度、失败数量和持久暂停状态；元数据主视图只显示聚合计数与当前最多 3 个刮削番号，不铺开逐任务列表；没有持久心跳证据的跨进程状态必须显示 unknown，不得伪造健康或以缺少 probe 冒充上游不可用；Windows DTO 与布局遵循 [Windows 设置与缓存客户端契约](contracts/windows-settings-cache-client.md)。
- **AC-122 `[IMP]`**: 管理员可暂停或恢复元数据新任务领取、查看并手动重试失败元数据任务、从影片详情显式重新刮削当前番号，对 `completed_with_warnings` 显式重试失败或缺失的可选富化阶段，取消排队或运行中的离线任务，并清理就绪缓存；暂停不中断运行中任务，恢复不创建或自动重试任务；富化重试不得自动重跑 JavDB 核心或付费 AI，Windows 操作白名单与显式阶段选择由 [TASK-208 Windows 设置与缓存客户端边界](changes/2026-07-30--task-208-settings-cache-client-boundaries.md) 和 [影片详情中文简介与重新刮削](changes/2026-08-03--movie-detail-chinese-description-rescrape.md) 冻结。
- **AC-150 `[IMP]`**: 管理员可在 Windows“设置 - 同步状态”中显式创建 MGDB 全量校对请求；保存数据源不隐式同步，未配置时不得入队，同模式活动请求幂等复用，只有终态请求时必须保留审计记录并使用空闲分钟槽新建请求；按钮在途禁用并在成功后显示已提交和刷新服务端状态；边界由 [TASK-324 MGDB 手动同步](changes/2026-08-05--task-324-mgdb-manual-sync.md) 冻结。

## 11. 部署、可靠性与验收

### REQ-023 Docker 部署与持久化

- **AC-123 `[IMP]`**: Docker Compose 至少包含 API、调度/工作进程和 PostgreSQL，数据库端口不得暴露到宿主公网。
- **AC-124 `[IMP]`**: PostgreSQL、媒体库永久图片、元数据清单缓存和必要日志使用独立持久化卷。
- **AC-125 `[IMP]`**: 后端只面向家庭网络或 VPN 部署，不提供公网部署向导。
- **AC-126 `[IMP]`**: 首版不创建自动数据库备份或图片备份任务。
- **AC-127 `[IMP]`**: API、工作进程和 PostgreSQL 提供健康检查；API 内部 live/ready 探针、worker/scheduler 容器内 ready 检查和 Schema head 门禁遵循运维健康契约，进程重启后任务状态可对账恢复。

### REQ-024 测试与外部验收

- **AC-128 `[IMP]`**: 默认自动测试不得访问真实 115、JavDB/DMM/GFriends 或真实 AI 付费接口，必须使用替身和固定样本；显式本机 provider 验收只允许无写 JavDB 登录、固定公开源和 AI models 读取，不得输出 secret；Phase 1 跨边界测试遵循 [TASK-014 后端元数据 E2E 确定性边界](changes/2026-07-27--task-014-e2e-boundaries.md)，115 协议测试遵循 [TASK-101 Cloud115 协议就绪边界](changes/2026-07-27--task-101-cloud115-readiness.md)，Phase 2 后端组合测试遵循 [TASK-113 115 缓存播放后端 E2E 边界](changes/2026-07-29--task-113-backend-e2e-boundaries.md)。
- **AC-129 `[IMP]`**: AVdb 解密、幂等导入、番号合并、分类标签、元数据超时、任务优先级、缓存状态机、安全删除、签名校验、播放进度和字幕生命周期都有自动测试；各工作流只对已交付算法负责，TASK-013 固化 Phase 1 测试清单，后续缓存与播放测试仍由对应任务交付。
- **AC-130 `[EXT]`**: Windows 发布前使用真实 115 验证扫码、离线、原画、HLS 回退、Range seek、字幕下载和安全清理；上游能力域漂移只按 [TASK-213 Cloud115 能力域兼容边界](changes/2026-07-31--task-213-cloud115-capability-host-compatibility.md) 扩展精确 HTTPS 子域白名单，真实 Range 按 [TASK-213 Range seek 证据串行化](changes/2026-08-01--task-213-range-seek-evidence-serialization.md) 与生产 seek 合并行为一致。TASK-213 本轮真实来源缺少外置字幕时，仅允许按 [外置字幕真实证据豁免](changes/2026-08-01--task-213-external-subtitle-evidence-waiver.md) 显式记录操作者批准的 `.srt` / `.ass` 跳过证据；字幕产品契约和默认自动测试不变。
- **AC-131 `[IMP]`**: HarmonyOS 开发前通过安装 SDK API 24 签名核验、ArkTS/ArkUI/能力构建检查和自动化契约 fixture 验证固定 User-Agent、302、Range、HLS、MKV 与 ASS 字幕的协议及状态语义；不要求连接、授权或侧载 API 24 物理真机，未运行真实设备验证不得宣称真实设备证据已通过。边界由 [HarmonyOS 工具链基线变更](changes/2026-08-04--harmony-baseline-and-device-gate.md) 冻结。
- **AC-132 `[SEF]`**: 单个外部元数据源、AI 或 GFriends 故障不会使已入库影片、排行榜快照或 115 播放整体不可用。

### REQ-025 首次连接与私有传输

- **AC-133 `[IMP]`**: 首次创建唯一管理员必须同时提供由 Docker Secret 或环境变量注入的一次性初始化口令；服务端常量时间校验，管理员创建后永久拒绝再次 bootstrap，口令不得入库、入日志或返回客户端。v1 后端进程仍要求该启动 secret 存在，但管理员创建后它永久失去初始化权限。
- **AC-134 `[IMP]`**: Docker Compose 默认只把 API 发布到 loopback；远程客户端必须通过 HTTPS 或可信加密 VPN 访问。显式启用的远程明文 HTTP 仅允许隔离私有地址并需要客户端风险确认，不提供公网明文或公网部署流程。
- **AC-135 `[IMP]`**: Windows 和 HarmonyOS 在登录前可配置并测试后端基址；地址作为非敏感本机设置保存，不得包含 userinfo、query 或 fragment。更换地址必须尝试注销旧服务端会话，并且无论旧服务端是否可达都清除本机令牌、字幕缓存和内存状态。

### REQ-026 GitHub 自动发布

- **AC-136 `[IMP]`**: pull request 与 `main` push 执行后端自包含测试/静态检查、Docker runtime 构建和 Windows analyze/test/release build；验证失败不得发布，默认流程不得读取业务 secret 或访问真实外部服务。
- **AC-137 `[IMP]`**: 正式发布只由严格 `vX.Y.Z` tag 触发，tag 必须与 Windows `pubspec.yaml` 的 SemVer 主版本一致；Flutter build number 只用于 Windows 资产版本。
- **AC-138 `[IMP]`**: Windows 发布生成 x64 私有 ZIP 和同名 `.sha256`，复用既有包内容、GPL/NOTICE、包内哈希与外层哈希验证。
- **AC-139 `[IMP]`**: 同一次构建把一个 Linux amd64 后端 runtime 镜像发布到 GHCR 与 Docker Hub，相同版本标签指向同一 digest；API、migrate、worker、scheduler 复用该 digest，两个仓库均提供完整 SemVer、major/minor、major、latest 和 Git SHA 标签。
- **AC-140 `[IMP]`**: tag 工作流只有在 Windows 与 Docker 发布路径均成功后才创建 GitHub Release，并上传 Windows ZIP 与外层 SHA-256，避免半发布版本。
- **AC-141 `[IMP]`**: GitHub Actions 使用默认只读和 job 级最小写权限，第三方 Action 固定完整 commit SHA；GitHub 操作只使用仓库 `GITHUB_TOKEN`，Docker Hub 只使用专用 `DOCKERHUB_TOKEN` Actions Secret，不得依赖个人 GitHub PAT 或业务 secret。
- **AC-142 `[IMP]`**: Windows 资产及 GHCR、Docker Hub 镜像 digest 生成 GitHub artifact attestation；Windows 公共构建明确为未签名，attestation 不冒充 Authenticode。
### REQ-027 Linux 一键私有部署

- **AC-143 `[IMP]`**: 正式 GitHub Release 同时提供固定版本的 Linux Docker 部署包和 SHA-256；部署包包含 Compose、无 secret 环境模板、一键安装脚本、部署说明和许可证/第三方声明，不包含 `.env`、secret、业务数据或移动版本引用。
- **AC-144 `[IMP]`**: Linux 一键安装自动生成五个用途独立的规范 Base64URL secret、收紧权限、创建完整 SemVer 发布配置并健康启动 Compose；重复运行不得覆盖有效配置或 secret，非法文件、用途复用和并发执行必须安全拒绝，默认保持 loopback 且任何输出不得包含 secret 值。

### REQ-028 Windows 单文件安装器

- **AC-145 `[IMP]`**: 正式 GitHub Release 除 Windows ZIP 外必须提供 `SakuraPlayer-Windows-X.Y.Z-B-Setup.exe` 及同名 `.sha256`；安装器必须来自同一份 Flutter x64 release bundle，包含应用 EXE、Flutter/native DLL、AOT/ICU 数据、许可证和第三方声明。
- **AC-146 `[IMP]`**: Windows 安装器必须由固定版本 Inno Setup 在 `windows-2022` 上构建，默认使用当前用户安装目录且不要求管理员权限；安装器和校验文件生成 GitHub artifact attestation，公共构建继续明确为 unsigned。
- **AC-147 `[IMP]`**: Linux 新手入口支持一条 `curl | bash` 命令自动解析最新正式 `vX.Y.Z` Release、下载对应 Docker 部署包、临时解压并调用包内安装器；不要求用户手动下载、解压或执行 SHA-256 校验，非法版本、下载失败和归档布局异常必须在 Compose 启动前失败并清理临时目录。
- **AC-148 `[IMP]`**: Linux `install-latest.sh` 默认把发布文件、`.env`、`secrets/` 和 bootstrap token 持久化到执行命令时的当前目录；首次交互安装可从 `/dev/tty` 选择合法 IPv4 发布地址和 `1..65535` API 端口，直接回车或无 TTY 使用 `127.0.0.1:8000`，已有 `.env` 保持原值，临时目录不得承载运行配置。
- **AC-149 `[IMP]`**: Linux Docker 的 PostgreSQL、永久图片、上游缓存和脱敏日志必须分别绑定到安装目录下的 `data/postgres/`、`data/catalog-images/`、`data/provider-cache/` 和 `data/app-logs/`；从旧版 named volume 升级时，一键安装必须在 Compose 启动前复制对应数据到这些目录，并将当前 `postgres_password.txt` 同步到既有数据库角色后再执行迁移，原 named volume 不得被自动删除。
- **AC-151 `[IMP]`**: 在现有安装目录重跑 Linux 一键入口必须把受支持的官方完整 SemVer 镜像原地升级到当前 Release，同时保留 `.env` 非镜像配置、secret、bind 数据、PostgreSQL、加密设置和已刮削目录；相同版本幂等，降级、自定义、本地、digest、latest、缺失或重复镜像配置必须在覆盖发布文件前拒绝，安装器不得执行 `down -v` 或删除旧 named volume。

## 12. 非功能要求

### NFR-001 性能

- 媒体库、排行榜和女优列表的已缓存 API 在单用户正常数据量下 p95 小于 500 ms。
- 全局搜索在规范化番号精确匹配时 p95 小于 300 ms，在标题/别名模糊匹配时 p95 小于 800 ms。
- WebSocket 状态从后端持久化提交到前台可见的延迟 p95 小于 2 秒。
- 播放入口在不计 115 上游响应时间时，签名校验和本地解析 p95 小于 200 ms。
- 29 万级资源导入必须采用流式或分批处理，单批失败不回滚已提交的其他批次。

### NFR-002 数据完整性

- 所有后台状态转换必须幂等并可从数据库恢复。
- 缓存创建、资源复用、播放租约和清理必须有数据库级互斥。
- 永久图片写入采用临时文件后原子替换，不留下半文件。
- 不提供旧 SakuraMedia 数据库迁移；检测到不兼容 Schema 时明确拒绝启动。

### NFR-003 可维护性

- 后端错误使用稳定错误码，客户端负责本地化文案。
- REST 契约使用 OpenAPI 版本化；WebSocket 事件包含版本、事件 ID 和任务快照版本。
- 运行配置、启动级密钥职责和客户端后端地址遵循版本化配置契约；不同密码学用途不得复用密钥。
- Windows 和 HarmonyOS 不共享 UI 代码，只共享 API 契约、错误码和领域语义。
- GPLv3 许可证、第三方声明和复用来源必须随发布产物保留。

## 13. 明确排除项

- Android、iOS、macOS、Linux、Web。
- 多用户、多管理员、多 115 账号。
- 公网直接暴露和公开应用商店上架。
- Nyaa、自定义磁力库、手动磁力、qBittorrent、Jackett 和通用下载器。
- 永久 115 媒体库、用户其他 115 目录扫描和后台热门预取。
- 订阅、新作推送、自动离线、多个播放列表和观看历史页面。
- 外部播放器、时间轴缩略图、评论、切片、相似推荐和视觉搜索。
- 自动备份、年龄确认和旧 SakuraMedia 数据库迁移。

## 14. 发布门禁

Windows v1 只有在 AC-001 至 AC-130、AC-133 至 AC-151 中适用于 Windows/后端的 `[IMP]` 项通过自动验证，且 AC-130 真实 115 检查全部通过后才能发布。HarmonyOS 工作只有在 Windows v1 门禁完成且 TASK-301 的 API 24 SDK 签名、构建和 fixture 基线通过后才能开始；不设置 API 24 物理真机连接门禁，AC-133 至 AC-135 的共享安全行为不得在鸿蒙端降级。GitHub 自动发布遵循 [GitHub 自动发布契约](contracts/github-release.md)。
