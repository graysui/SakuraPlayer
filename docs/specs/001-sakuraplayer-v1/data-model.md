# SakuraPlayer v1 数据模型

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**创建日期**: 2026-07-24

**数据库**: PostgreSQL 17.5

## 1. 建模规则

- “影片”和“AVdb 来源帖子”是不同实体：一部影片可以关联多个来源。
- 只有标记为 `规格` 的实体、字段或约束直接来自验收条件；标记为 `(derived)` 的内容是技术实现建议，不产生新的产品验收条件。
- 所有时间使用 UTC `timestamptz`；调度时区单独保存为 `Asia/Shanghai`。
- 外部 ID 一律按字符串保存，避免 115/JavDB 数值范围和前导零问题。
- 磁力、Cookie、AI key 和 JavDB 密码使用加密载荷；完整明文不进入日志、事件或响应。
- 115 原画/HLS URL、字幕正文和客户端字幕本地路径不入数据库。
- 表名和字段名在实现时可按迁移规范微调，但关系、不变量和状态语义不可改变。

### 1.1 来源标记

| 标记 | 含义 |
|---|---|
| `AC-nnn` | 规格明确要求 |
| `NFR-nnn` | 非功能规格明确要求 |
| `(derived)` | 为实现规格推导的结构，不是独立产品要求 |

## 2. 聚合关系

```text
AdminUser 1 --- N RefreshSession
AdminUser 1 --- 0..1 Cloud115Binding

AvdbSyncRun 1 --- N AvdbAsset
Movie 1 --- N ResourceSource
ResourceSource 1 --- N ResourceSourceLabel
ResourceSource 1 --- 0..1 SourceRejection

Movie N --- N Actor
Movie N --- N Tag
Movie 1 --- N CatalogImage
Actor 1 --- N ActorAlias
Actor 1 --- N CatalogImage
Movie 1 --- N MetadataJob
MetadataJob 1 --- N MetadataStage
Movie/Actor 1 --- N TranslationRecord

RankingSnapshot 1 --- N RankingEntry
Movie/Actor 1 --- 0..1 Favorite

ResourceSource 1 --- N CacheJob
CacheJob 1 --- N RemoteMedia
RemoteMedia 1 --- N RemoteSubtitle
CacheJob 1 --- N PlaybackSession
PlaybackSession 1 --- 0..1 PlaybackLease
Movie 1 --- 0..1 MoviePlaybackState

Domain aggregate 1 --- N DomainEvent
```

## 3. 身份与配置

### 3.1 `admin_user`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 唯一管理员固定一行 | AC-001 |
| `singleton_key` | boolean | 固定为 true 且唯一，数据库级限制全表最多一行 | AC-001 `(derived)` |
| `username` | varchar(64) | 唯一、非空 | AC-001 |
| `password_hash` | text | Argon2id，永不返回 | AC-010 |
| `session_epoch` | bigint | 退出/全局撤销时递增 | `(derived)`，支持 AC-011/102 |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | `(derived)` |

**不变量**: 数据库检查或引导事务保证全表最多一行；不存在注册列表和角色表。AC-133 的 bootstrap token 只从启动 secret 读取，在 bootstrap 事务锁内先确认管理员不存在后再常量时间校验，不建立数据库字段或哈希记录。

### 3.2 `refresh_session`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `admin_id` | UUID | 外键 | AC-011 |
| `token_hash` | bytea | 当前 refresh JWT 的 SHA-256，固定 32 字节 | AC-011 |
| `client_instance_id` | UUID | Windows/HarmonyOS 本机实例 | `(derived)` |
| `expires_at` | timestamptz | 非空 | AC-011 |
| `revoked_at` | timestamptz | 可空 | AC-011/012 |
| `last_used_at` | timestamptz | 可空 | `(derived)` |

**不变量**: 同一 `admin_id + client_instance_id` 最多一条 `revoked_at IS NULL` 会话。刷新在行锁事务内轮换当前 hash，不延长 `expires_at`；已签名旧 token 的 hash 不匹配视为重放并撤销该会话。

### 3.3 `encrypted_setting`

用于 115 Cookie、AI key、可选 JavDB 凭据等可恢复秘密。JavDB 用户名和密码使用单个 `javdb.credentials` 加密 JSON envelope 原子 CAS，避免跨键混合版本。普通非敏感配置使用同一记录的 `public_value`，但同一键不能同时存在明文和密文。秘密 clear 后以内部无秘密 tombstone 保留递增版本；旧客户端不能用清空前版本覆盖后续新配置。

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `key` | varchar(128) | 主键，如 `ai.api_key` | AC-014/046/054/120 |
| `public_value` | jsonb | 仅非敏感配置 | `(derived)` |
| `key_id` | varchar(64) | 主密钥版本 | `(derived)` |
| `nonce` | bytea | 每次随机 12 字节 | `(derived)` |
| `ciphertext` | bytea | AES-256-GCM 密文和 tag | AC-014 |
| `version` | bigint | 乐观并发 CAS | AC-015 |
| `updated_at` | timestamptz | 非空 | `(derived)` |

**客户端本机配置**: AC-135 的 `api_base_url` 不进入后端数据库。Windows 使用普通本机配置存储，HarmonyOS 使用 Preferences 等非秘密存储；令牌仍使用各平台安全存储。更换地址先尝试撤销旧服务端会话，并始终丢弃本机令牌、字幕和内存快照。

### 3.4 `cloud115_binding`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 单例主键 | AC-001/079 |
| `singleton_key` | boolean | 固定 true 且唯一，数据库级限制整表最多一行 | `(derived)` |
| `account_key` | varchar(128) | 由 UID 等稳定字段派生，不是 Cookie | AC-080 |
| `display_name` | varchar(128) | 可空、脱敏展示 | `(derived)` |
| `cookie_setting_key` | varchar(128) | 指向加密设置 | AC-014 |
| `login_app` | varchar(32) | 115 登录槽 | `(derived)` |
| `cache_root_cid` | varchar(64) | `SakuraPlayer-Cache` CID | AC-079/080 |
| `status` | enum | `active/expired/unavailable/detached` | AC-016/082 |
| `credential_version` | bigint | 扫码或 Cookie CAS 成功递增 | AC-015 |
| `last_verified_at` | timestamptz | 可空 | AC-119/121 |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | `(derived)` |

**不变量**: 整表最多一行；Cookie 固定使用 `encrypted_setting.key=cloud115.cookie`，
`encrypted_setting.version` 是唯一凭据版本真相，`credential_version` 在同一事务中镜像相同
值。快照写回同时比较两处起始版本，防止旧请求覆盖重新扫码。

## 4. AVdb 资源接入

### 4.0 `avdb_sync_request` `(derived)`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `mode` | enum | `incremental_30d/full_reconcile` | 支持 AC-020/021 |
| `scheduled_for` | timestamptz | 调度触发的 UTC 分钟槽 | `(derived)` |
| `status` | enum | `queued/claimed/completed/failed` | `(derived)` |
| `claim_owner` | varchar(64) | 可空；claimed 时为 worker 实例 | `(derived)` |
| `claim_token` | UUID | claimed 时非空，防止过期 worker 以相同 owner 收尾 | `(derived)` |
| `claimed_at` | timestamptz | 可空；保留最近 claim 时间 | `(derived)` |
| `claim_expires_at` | timestamptz | 可空；心跳续租，过期后允许重新 claim | `(derived)` |
| `attempt_count` | integer | 从 0 单调递增 | `(derived)` |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `completed_at` | timestamptz | 可空 | `(derived)` |
| `failure_code` | varchar(128) | 可空；稳定错误码 | 支持 AC-024 |
| `failure_detail` | text | 可空；只保存脱敏摘要 | 支持 AC-024 |
| `sync_run_id` | UUID | 成功时关联运行；禁止删除被引用运行 | `(derived)` |

唯一键 `(mode, scheduled_for)` 合并 scheduler 的同槽重复触发。claim 收尾以 `id + owner + token + 未过期租约` 为 CAS 条件；该表只表达待执行请求，Release、资产、游标、结果和失败事实仍由 `avdb_sync_run` 与 `avdb_asset` 持有，scheduler 不执行下载或导入业务。

### 4.1 `avdb_sync_run`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `mode` | enum | `incremental_30d/full_reconcile` | AC-020/021 |
| `repository` | varchar(128) | 实际使用主/备源 | AC-019 |
| `release_id` | varchar(128) | 上游 Release 唯一值 | AC-024 |
| `status` | enum | `running/completed/failed` | AC-024 |
| `cursor` | jsonb | 已处理资产与批次位置 | AC-024 |
| `started_at` | timestamptz | 非空 | AC-024 |
| `completed_at` | timestamptz | 可空 | AC-024 |
| `failure_code` | varchar(128) | 可空、稳定错误码 | AC-024 |
| `failure_detail` | text | 可空、脱敏 | AC-024 |
| `stats` | jsonb | 插入/更新/跳过/待识别统计 | `(derived)` |
| `claim_token` | UUID | running 时非空，防止旧 worker 更新 | `(derived)` |
| `claim_expires_at` | timestamptz | running 租约；批次推进时续租 | `(derived)` |
| `attempt_count` | bigint | 至少 1；恢复时递增 | `(derived)` |

唯一键 `(repository, release_id, mode)` 防止重复导入同一 Release。`completed` 永久幂等；`failed` 或租约过期的 `running` 可由新 claim 按游标恢复，活动租约不得被并发接管。

### 4.2 `avdb_asset`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `sync_run_id` | UUID | 外键 | `(derived)` |
| `asset_name` | varchar(255) | 期望文件名 | AC-018/019 |
| `sha256` | char(64) | 下载时计算 | AC-019/024 |
| `byte_size` | bigint | 正数 | `(derived)` |
| `manifest` | jsonb | 不含密钥材料的解密参数摘要 | AC-018/024 |
| `status` | enum | `downloaded/verified/decrypted/imported/failed` | `(derived)` |

### 4.3 `resource_source`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `website` | varchar(32) | `sehuatang/x1080x` 等 | AC-031 |
| `external_post_id` | bigint | AVdb `tid` | AC-031 |
| `movie_id` | UUID | 可空；待识别时为空 | AC-028/029/031 |
| `raw_number` | varchar(128) | 原始番号 | AC-030 |
| `normalized_number` | varchar(128) | 可空 | AC-028/030 |
| `title` | text | 原始标题 | AC-031 |
| `publish_date` | date | 可空 | AC-026/041 |
| `section` | varchar(64) | 六目标分类之一 | AC-025 |
| `category` | varchar(128) | 可空 | AC-034 |
| `resource_size_mb` | bigint | AVdb `size`，可空 | AC-035 |
| `detail_url` | text | 上游帖子链接 | `(derived)` |
| `preview_urls` | jsonb | 原始预览 URL 列表 | `(derived)` |
| `magnet_key_id` | varchar(64) | 可空 | `(derived)` |
| `magnet_nonce` | bytea | 可空 | `(derived)` |
| `magnet_ciphertext` | bytea | 拒绝后必须清空 | AC-017/036 |
| `identification_status` | enum | `identified/pending/manual/rejected` | AC-028/029/036 |
| `source_created_at` | timestamptz | AVdb `create_time` | `(derived)` |
| `source_updated_at` | timestamptz | AVdb `update_time` | `(derived)` |
| `imported_at` | timestamptz | 非空 | `(derived)` |

唯一键 `(website, external_post_id)`。全量对账缺失不会删除或禁用既有行。`movie_id IS NULL` 的行不能进入媒体库或自动元数据队列。

### 4.4 `resource_source_label`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `source_id` | UUID | 外键 | AC-033 |
| `label` | enum | `subtitle/cracked/4k/censored` | AC-033/034 |
| `evidence` | varchar(255) | 如 `section=中文字幕` | AC-034 |
| `created_at` | timestamptz | 非空 | `(derived)` |

主键 `(source_id, label)`。标签可叠加且相互不排斥。

### 4.5 `source_rejection`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `website` | varchar(32) | 来源网站 | AC-036 |
| `external_post_id` | bigint | 来源帖子 ID | AC-036 |
| `reason_code` | varchar(128) | 失效/违规/无法离线 | AC-036 |
| `rejected_at` | timestamptz | 非空 | AC-036 |
| `last_seen_release_id` | varchar(128) | 可空 | `(derived)` |

唯一键 `(website, external_post_id)`。表中禁止磁力、标题全文和上游响应正文；同步先查拒绝标记并跳过重建来源。
拒绝与来源导入对同一 `(website, external_post_id)` 使用相同的 PostgreSQL 事务级 advisory lock；拒绝事务提交后，后续增量或全量导入不得恢复来源磁力。

## 5. 目录与元数据

### 5.1 `movie`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `normalized_number` | varchar(128) | 唯一、非空 | AC-030 |
| `raw_numbers` | jsonb | 原始番号与别名 | AC-030 |
| `javdb_id` | varchar(128) | 可空、唯一非空 | AC-044 |
| `title_original` | text | 核心元数据 | AC-042/074 |
| `title_zh` | text | 可空，AI 译文 | AC-055/074 |
| `release_date` | date | 可空 | AC-074 |
| `maker` | varchar(255) | 可空 | AC-056/074 |
| `series` | varchar(255) | 可空 | AC-056/074 |
| `director` | varchar(255) | 可空 | AC-074 |
| `description_original` | text | JavDB/DMM 原文，可空 | AC-045/074 |
| `description_zh` | text | 可空 | AC-055/074 |
| `score` | numeric(5,2) | 可空 | AC-074 |
| `catalog_state` | enum | `raw_only/metadata_queued/metadata_running/core_ready` | AC-042/067 |
| `metadata_updated_at` | timestamptz | 可空 | `(derived)` |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | `(derived)` |

正式列表和详情必须过滤 `catalog_state=core_ready`。

### 5.2 `actor` 与 `actor_alias`

`actor`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `javdb_id` | varchar(128) | 唯一非空；姓名不是主键 | AC-044/050 |
| `name_ja` | varchar(255) | 可空 | AC-050/076 |
| `name_zh` | varchar(255) | 可空 | AC-050/076 |
| `bio_original` | text | 可空 | AC-050 |
| `bio_zh` | text | 可空 | AC-050/055 |
| `bio_zh_source` | enum | `actor_mapping/ai`；与 bio_zh 同时为空或非空 | AC-050/055 |
| `gender` | enum | `female/male/unknown` | `(derived)` |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | `(derived)` |

`actor_alias`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `actor_id` | UUID | 外键 | AC-050 |
| `alias` | varchar(255) | 权威原文 | AC-050 |
| `normalized_alias` | varchar(255) | casefold/空白归一 | `(derived)` |
| `authority` | enum | `javdb/actor_mapping` | AC-050/051 |

主键 `(actor_id, normalized_alias)`。搜索词不得写入此表。歧义别名可以存在于多个演员，但 GFriends 匹配时必须拒绝非唯一结果。

### 5.3 关系表

| 表 | 主键 | 规则 | 来源 |
|---|---|---|---|
| `movie_actor` | `(movie_id, actor_id)` | 保存来源顺序 `(derived)` | AC-042/044/074 |
| `tag` | `id` | `name` 唯一 | AC-056/074 |
| `movie_tag` | `(movie_id, tag_id)` | AI 不得自由改写 | AC-056 |

### 5.4 `catalog_image`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `owner_type` | enum | `movie/actor` | AC-047/076 |
| `owner_id` | UUID | 逻辑外键 | `(derived)` |
| `kind` | enum | `cover/plot/profile/placeholder` | AC-047/048 |
| `source_url` | text | 可空、白名单 URL | `(derived)` |
| `position` | integer | 同 owner/kind 内从 0 开始，封面固定为 0 | `(derived)` |
| `relative_path` | text | 永久卷相对路径 | AC-047 |
| `sha256` | char(64) | 内容摘要 | `(derived)` |
| `status` | enum | `ready/placeholder/retry_pending`；已有成功图片待替换时 `retry_pending` 可继续指向最近 ready 文件 | AC-048 |
| `created_at` | timestamptz | 非空 | `(derived)` |

写入必须临时文件 + 原子替换。GFriends 图不进入此表，除非它被明确选作永久目录图片且规格后续变更；v1 只保存 GFriends URL 索引。

### 5.5 `metadata_job` 与 `metadata_stage`

`metadata_queue_state` 以固定 `singleton_key=true` 保存首批范围的 `initial_as_of`、`initial_completed_at` 和更新时间。worker 分批入队时必须复用冻结日期；完成标记后不得因重启或新来源把后续影片重新归入 initial。读取 initial 剩余额度、初始化状态行和整批入队必须处于同一 PostgreSQL advisory lock 生命周期，保证多 worker 下不超过 5000 部。候选查询 anti-join 已有任意 attempt 的影片并继续补足新任务，不得因失败影片仍为 `raw_only` 而阻塞或反复扫描后续 initial/history 候选，也不得借此自动重试失败任务。

`metadata_job`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `movie_id` | UUID | 外键 | AC-037 |
| `normalized_number` | varchar(128) | 任务稳定输入 | AC-037 |
| `priority` | smallint | 10/20/30/40/50 | AC-041 |
| `reason` | enum | `manual_or_search/ranking/daily/initial/history` | AC-041 |
| `sort_date` | date | 可空；创建 attempt 时冻结的来源发布日期排序键 | AC-041 |
| `retry_mode` | enum | `full/missing_enrichment`；默认 `full` | AC-122 |
| `requested_stages` | jsonb | 富化重试只允许 `images/dmm/actor_map/gfriends/translation`；完整任务为空 | AC-122 |
| `status` | enum | `queued/running/completed/completed_with_warnings/failed` | AC-037/040 |
| `attempt_no` | integer | 手动重试递增 | AC-040/043 |
| `parent_job_id` | UUID | 可空，指向被手动重试任务 | `(derived)` |
| `claim_owner` | varchar(128) | 可空 | `(derived)` |
| `claim_expires_at` | timestamptz | 可空 | `(derived)` |
| `started_at` | timestamptz | 可空 | AC-043 |
| `finished_at` | timestamptz | 可空 | AC-043 |
| `elapsed_ms` | bigint | 可空 | AC-043 |
| `failure_code` | varchar(128) | 可空 | AC-039/043 |
| `failure_detail` | text | 可空、脱敏 | AC-043 |
| `created_at` | timestamptz | 非空 | `(derived)` |

部分唯一索引保证同一 `normalized_number` 最多一条 `queued/running`。同优先级按 `sort_date DESC NULLS LAST, created_at ASC, id ASC` claim；重试继承父任务 `sort_date`。失败或 warning 行永不由 worker 改回 queued；重试插入带 `parent_job_id` 的新行。`missing_enrichment` 的 `requested_stages` 必须非空且禁止 `javdb_core`，未列出的 stage 直接记为 `skipped`。

用户搜索 exact number 时允许在影片行锁事务内把既有 `queued` attempt 原子改为 `priority=10, reason=manual_or_search`；`running` 只复用，最近 attempt 为 `failed` 时不得自动创建新 attempt。

`metadata_stage`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `job_id` | UUID | 外键 | AC-043 |
| `stage` | enum | `javdb_core/images/dmm/actor_map/gfriends/translation` | AC-042/043 |
| `status` | enum | `pending/running/succeeded/warning/failed/skipped` | AC-042/043 |
| `started_at` | timestamptz | 可空 | AC-043 |
| `finished_at` | timestamptz | 可空 | AC-043 |
| `failure_code` | varchar(128) | 可空 | AC-043 |

主键 `(job_id, stage)`。

### 5.6 `translation_record`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `owner_type` | enum | `movie_title/movie_description/actor_bio` | AC-055 |
| `owner_id` | UUID | 非空 | `(derived)` |
| `source_text` | text | 原文 | AC-057 |
| `source_hash` | char(64) | 内容摘要 | AC-057 |
| `translated_text` | text | 可空；completed 时非空译文 | AC-057 |
| `model` | varchar(255) | 非空 | AC-054/057 |
| `prompt_version` | varchar(64) | 非空 | AC-057 |
| `status` | enum | `reserved/dispatched/completed/rejected/unknown` | AC-057 |
| `claim_token` | UUID | reserved/dispatched 时非空 | `(derived)` |
| `claim_expires_at` | timestamptz | 仅 reserved 非空 | `(derived)` |
| `dispatch_started_at` | timestamptz | dispatched 及其终态非空 | AC-057 |
| `failure_code` | varchar(128) | rejected/unknown 时非空 | AC-057 |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | `(derived)` |

唯一键 `(owner_type, owner_id, source_hash, model, prompt_version)`。`source_hash` 固定为未规范化 source_text UTF-8 的 SHA-256。reserved 在 lease 过期且尚未进入 dispatched 时可用新 token 回收；进入 dispatched 前必须先提交事务。dispatched/completed/rejected/unknown 均不得由自动任务重新派发。completed 命中直接复用；rejected/unknown 保存付费或可能付费但不可用的事实。

状态形状：reserved 只有 claim token/expiry；dispatched 有 token 和 dispatch time、无 expiry；completed 有译文且无 failure；rejected/unknown 有 dispatch time 和 failure code、无译文。数据库 check 约束状态形状，trigger 禁止 dispatched 及其终态回到 reserved，并禁止 completed/rejected/unknown 被修改。

### 5.7 上游索引快照

`provider_snapshot_request`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `scheduled_for` | timestamptz | UTC 分钟槽；唯一 | AC-049 |
| `status` | enum | `queued/claimed/completed/failed` | AC-049 |
| `claim_owner` | varchar(128) | 可空 | `(derived)` |
| `claim_token` | UUID | 可空；每次 claim 唯一 | `(derived)` |
| `claim_expires_at` | timestamptz | 可空；过期可回收同一请求 | `(derived)` |
| `attempt_count` | integer | >= 0 | `(derived)` |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `completed_at` | timestamptz | 可空 | `(derived)` |
| `failure_code` | varchar(128) | 可空、稳定码 | AC-049 |

scheduler 只插入请求。worker 以 `FOR UPDATE SKIP LOCKED` claim；同一 `scheduled_for` 重复入队返回既有请求，不为明确失败自动插入新请求。

`actor_mapping_snapshot` 与 `gfriends_snapshot` 使用相同结构：

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `sha256` | char(64) | 每个来源内唯一 | AC-049 |
| `byte_size` | bigint | 正数且不超过来源上限 | `(derived)` |
| `relative_path` | text | provider-cache 服务端相对路径 | AC-049/052 |
| `status` | enum | `current/superseded` | AC-049 |
| `fetched_at` | timestamptz | 非空 | AC-049 |
| `activated_at` | timestamptz | 非空 | `(derived)` |

每张快照表用部分唯一索引保证最多一个 `current`。只有完整验证并已原子写入的文件能入表；同摘要幂等复用，激活新快照时在同一事务把旧 current 改为 superseded。

`gfriends_actor_asset`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `actor_id` | UUID | 外键 | AC-051 |
| `snapshot_id` | UUID | 外键到 current GFriends 快照 | AC-049/052 |
| `asset_kind` | enum | `profile/gallery` | AC-051/052 |
| `position` | integer | 同 actor 从 0 开始；profile 固定 0 | `(derived)` |
| `url` | text | 固定 Content 基址下的 HTTPS URL；全局唯一 | AC-051/052 |
| `match_name` | varchar(255) | 产生唯一匹配的原始名称 | AC-051 |
| `created_at` | timestamptz | 非空 | `(derived)` |

一次成功重建在同一事务替换全部 `gfriends_actor_asset`，并以唯一 `(actor_id, asset_kind, position)` 和全局 `url` 防止重复或跨演员复用。GFriends 图不进入 `catalog_image`。

## 6. 发现与收藏

### 6.1 `ranking_sync_request`、`ranking_snapshot` 与 `ranking_entry`

`ranking_sync_request`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `board` | enum | `daily/weekly/monthly/top250` | AC-070 |
| `year` | smallint | 仅 top250 可填，2008..2200；运行时不得超过当前年 | AC-070 |
| `scheduled_for` | timestamptz | 调度触发 UTC 分钟槽 | `(derived)` |
| `status` | enum | `queued/claimed/completed/failed` | AC-069/073 |
| `claim_owner` | varchar(128) | claimed 时非空 | `(derived)` |
| `claim_token` | UUID | claimed 时非空，隔离过期 worker | `(derived)` |
| `claim_expires_at` | timestamptz | claimed 时非空，heartbeat 续租 | `(derived)` |
| `attempt_count` | bigint | 从 0 单调递增 | `(derived)` |
| `snapshot_id` | UUID | completed 时指向激活快照 | `(derived)` |
| `completed_at` | timestamptz | 终态非空 | `(derived)` |
| `failure_code` | varchar(128) | failed 时稳定错误码 | AC-073 |
| `created_at` | timestamptz | 非空 | `(derived)` |

唯一 `(board, COALESCE(year, 0), scheduled_for)` 合并同槽重复调度；部分唯一索引
保证同一 `(board, COALESCE(year, 0))` 最多一个 `queued/claimed`。claim/renew/finish
必须匹配 id、owner、token 和未过期 lease。失败详情不保存上游正文、凭据、token 或
完整 URL。

`ranking_snapshot`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `board` | enum | `daily/weekly/monthly/top250` | AC-070 |
| `year` | smallint | 仅 top250 可填，null 表示总榜 | AC-070 |
| `status` | enum | `building/current/superseded` | AC-069/073 |
| `source_synced_at` | timestamptz | 成功取得并验证候选的 UTC 时间 | AC-069 |
| `created_at` | timestamptz | 非空 | `(derived)` |

部分唯一索引保证每个 `(board, COALESCE(year, 0))` 最多一个 current。候选快照和
全部条目在短事务内写入，随后旧 current 改 superseded、候选改 current；building
不会在提交后对查询可见。失败只终结 request，不创建或激活 failed snapshot。

`ranking_entry`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `snapshot_id` | UUID | 外键，删除快照时级联 | AC-069 |
| `rank` | integer | 正数，保留上游原始名次 | AC-069 |
| `normalized_number` | varchar(128) | 非空 | `(derived)` |
| `movie_id` | UUID | 可空，指向同步时已存在的影片 | AC-071/072 |

主键 `(snapshot_id, rank)`，并唯一 `(snapshot_id, normalized_number)`。非法番号跳过，
重复番号只保留第一次，允许 rank 间隙。查询按 normalized_number 重新关联当前 Movie，
只输出有活动来源且 `core_ready` 的条目；有来源但未完成核心时幂等创建或提升
priority 20。cursor 绑定 snapshot ID 和最后可见 rank，current 切换后继续读取同一
superseded 快照。空或全无效候选不激活，新同步失败不改变 current。

### 6.2 `favorite`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `target_type` | enum | `movie/actor` | AC-077 |
| `target_id` | UUID | 非空 | AC-077 |
| `created_at` | timestamptz | 非空 | `(derived)` |

唯一键 `(target_type, target_id)`。写入服务必须先验证目标可见：影片为 `core_ready` 且有活动来源；演员至少关联一部该类影片。无列表名、排序和自定义播放列表实体。影片收藏复用媒体库排序；演员收藏按规范化展示名、actor ID 稳定排序。

### 6.3 目录查询确定性 `(derived)`

- category 多选为 OR，label 多选为 AND；全部来源条件必须由同一活动 identified/manual 来源满足。
- 影片发布日期排序键是满足来源筛选的 `MAX(resource_source.publish_date)`，null 永远最后，movie ID 为 tie-breaker。
- cursor 是版本化 Base64URL JSON 并绑定查询、筛选、排序和 favorite；跨查询复用无效。
- Phase 1 通过空 `SourceAvailabilityPort` 和 `PlaybackStatePort` 返回 `available`/null，不建立未来 cache/playback 表。
- 影片详情和演员详情中的每个集合使用确定性顺序并限制为 100 项。

## 7. 115 缓存

### 7.1 `cache_job`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `movie_id` | UUID | 外键 | AC-084 |
| `source_id` | UUID | 外键，只能来自 AVdb | AC-083/084 |
| `binding_id` | UUID | 可空外键；活动时非空，解绑后 `ON DELETE SET NULL` | AC-080 |
| `status` | enum | 见 10.2 | AC-085..098 |
| `capacity_class` | enum | `queued/running/ready/released`，见 10.2 | AC-085 |
| `account_key` | varchar(128) | 创建时快照 | AC-080/081 |
| `cache_root_cid` | varchar(64) | 创建时快照 | AC-080/081 |
| `task_dir_cid` | varchar(64) | 提交前创建，可空 | AC-080/081 |
| `task_dir_name` | varchar(128) | 随机且不可由标题控制 | `(derived)` |
| `remote_info_hash` | varchar(128) | 115 远端任务 ID，可空 | `(derived)` |
| `submit_started_at` | timestamptz | 可空；外部提交前持久化，非空后禁止自动重提 | `(derived)` |
| `remote_percent` | numeric(5,2) | 0..100 | `(derived)` |
| `ready_at` | timestamptz | 可空 | AC-094 |
| `last_accessed_at` | timestamptz | 可空 | AC-094/095 |
| `expires_at` | timestamptz | 可空 | AC-094 |
| `claim_owner` | varchar(128) | 可空 | `(derived)` |
| `claim_token` | UUID | 可空；隔离过期 worker | `(derived)` |
| `claim_expires_at` | timestamptz | 可空 | `(derived)` |
| `failure_code` | varchar(128) | 可空 | AC-098/121 |
| `failure_detail` | text | 可空、脱敏 | AC-121 |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | `(derived)` |

**索引和约束**:

- 同一 `source_id + binding_id` 最多一个活动状态任务，保证重复点击复用。
- 状态与 `capacity_class` 使用 check constraint 固定形状；`cancelling` 保留原类别。
- PostgreSQL advisory transaction lock 内计数保证 running 最多 2、queued 最多 10。
- `task_dir_cid` 非空时唯一。
- claim owner/token/expiry 必须同时为空或同时非空；claim 写入使用未过期 token CAS。
- `remote_info_hash` 要求任务目录和提交开始事实均存在；`submit_uncertain` 要求无 remote ID、
  固定错误码并保留 running 容量。
- TASK-105 增加 ready 至少一个有效 `remote_media` 和有序选择归属约束。
- `awaiting_selection/ready` 首次物化时 `ready_at/last_accessed_at/expires_at` 必须同时非空；
  TTL 设置变更不批量改写已有行。
- ready capacity 的 20 是安全删除完成后的收敛目标；`cleaning/cleanup_failed` 在删除确认前继续
  占用容量，禁止用状态预释放伪造硬上限。
- 60 秒等待不保存为任务状态。

### 7.1.1 `cache_play_request`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `idempotency_key` | varchar(128) | 主键；固定安全 ASCII | AC-091 |
| `movie_id` | UUID | 请求影片 | AC-084/091 |
| `source_id` | UUID | 请求来源 | AC-083/091 |
| `cache_job_id` | UUID | 返回的任务，RESTRICT | AC-091 |
| `created_at` | timestamptz | 非空 | `(derived)` |

同 key、同 movie/source 永久返回同一任务；同 key 不同 payload 返回
`idempotency_conflict`。不同 key 复用同一活动任务时各自保留请求事实。

### 7.2 `remote_media`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `cache_job_id` | UUID | 外键，清理后级联删除 | AC-092/093 |
| `file_id` | varchar(64) | 115 文件 ID | `(derived)` |
| `pickcode` | varchar(128) | 播放稳定定位 | `(derived)` |
| `parent_cid` | varchar(64) | 必须为任务目录或受控子目录 | AC-081/098 |
| `name` | text | 文件名 | AC-093 |
| `size_bytes` | bigint | 真实视频文件大小 | AC-035 |
| `duration_seconds` | bigint | 可空 | `(derived)` |
| `candidate_id` | UUID | 同一连续分段共享候选组，单文件独立 | AC-093 |
| `sequence_no` | integer | 候选组内分段顺序，从 0 开始 | AC-093 |
| `selection_score` | integer | 广告/样片/番号等评分 | `(derived)` |
| `selection_evidence` | jsonb | 稳定 reason/value 列表，不含短链或外部正文 | `(derived)` |
| `is_valid` | boolean | 通过扩展名和排除规则 | AC-092 |
| `created_at` | timestamptz | 非空 | `(derived)` |

唯一键 `(cache_job_id, file_id)` 和 `(cache_job_id, candidate_id, sequence_no)`。禁止保存
原画/HLS URL。

`cache_job_media_selection` 由 TASK-105 迁移，主键 `(cache_job_id, sequence_no)`，并唯一
`(cache_job_id, media_id)`；它是 OpenAPI `selected_media_ids` 的有序来源。

### 7.3 `remote_subtitle`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `cache_job_id` | UUID | 外键 | AC-108 |
| `media_id` | UUID | 可空，同名匹配到同一 `cache_job_id` 的具体视频 | AC-109 |
| `file_id` | varchar(64) | 115 文件 ID | `(derived)` |
| `pickcode` | varchar(128) | 字幕下载定位 | `(derived)` |
| `parent_cid` | varchar(64) | 受管目录内 | AC-108 |
| `name` | text | 文件名 | AC-108/109 |
| `extension` | enum | `srt/ass/ssa/vtt` | AC-108 |
| `size_bytes` | bigint | 下载上限检查 | `(derived)` |
| `match_score` | integer | 同名优先 | AC-109 |
| `match_evidence` | jsonb | 稳定同名/同目录证据 | AC-109 |
| `created_at` | timestamptz | 非空 | `(derived)` |

数据库不保存字幕正文和客户端副本路径。manifest 只发布 `media_id IS NULL` 或属于当前完整已选
媒体队列的字幕；下载时非空 `media_id` 必须与 path 中 playback session 的媒体一致。

### 7.4 `cache_cleanup_attempt`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `cache_job_id` | UUID | 外键 | AC-098 |
| `attempt_no` | integer | 每 job 从 1 递增；与 job 联合唯一 | AC-098/121 |
| `ownership_evidence` | jsonb | 只含账号摘要和 CID，不含 Cookie | AC-081/098 |
| `status` | enum | `running/succeeded/failed/detached`；单 job 最多一个 running | AC-098 |
| `failure_code` | varchar(128) | 可空 | AC-098 |
| `started_at` | timestamptz | 非空 | `(derived)` |
| `finished_at` | timestamptz | 可空 | `(derived)` |

running 必须 `finished_at/failure_code` 为空；succeeded/detached 必须 finished 且无 failure；failed
必须 finished 且有稳定 failure_code。清理执行复用 CacheJob claim owner/token/expiry fencing；删除
后崩溃由下一 attempt 的 task directory not-found 收敛。远端确认后，同一事务先转 cleaned，再删
selection/media/subtitle；remote media 删除级联删除对应 playback session/lease。

## 8. 播放

### 8.1 `playback_session`

TASK-107 创建下表的最小持久 Schema 以解除 lease 外键依赖环；TASK-108 才提供会话签发、签名、
stream 和公开 API 行为。

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `admin_id` | UUID | owner | AC-102 |
| `session_epoch` | bigint | 签发时快照 | `(derived)` |
| `movie_id` | UUID | 外键 | AC-111 |
| `cache_job_id` | UUID | 必须 ready | AC-099/102 |
| `media_id` | UUID | 属于缓存任务 | AC-099/102 |
| `mode` | enum | `original/compatibility` | AC-101/103 |
| `platform` | enum | `windows/harmonyos` | AC-100 |
| `user_agent_hash` | char(64) | 固定 UA 的摘要 | AC-100/102 |
| `issued_at` | timestamptz | 非空 | AC-099 |
| `expires_at` | timestamptz | 固定 12 小时 | AC-099 |
| `revoked_at` | timestamptz | 可空 | `(derived)` |

签名载荷包含 ID、owner/session epoch、模式、UA 摘要和过期时间。TASK-108 的 session 创建只接受
`original`；TASK-109 扩展为 `original/compatibility`。完整有序选择中的每个媒体有独立 session/lease，
但共用签发时刻、过期时刻、owner、平台和 client instance。上游 URL 不保存。
`(cache_job_id, media_id)` 外键保证媒体归属并使用 `ON DELETE CASCADE`；安全清理删除 media 时
同时删除已无有效租约的 session/lease。lease 获取与清理选择共同锁 CacheJob，且只允许 ready。

### 8.2 `playback_lease`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `playback_session_id` | UUID | 唯一活动租约 | AC-096 |
| `client_instance_id` | UUID | 非空 | `(derived)` |
| `last_heartbeat_at` | timestamptz | 非空 | AC-096 |
| `expires_at` | timestamptz | 非空 | AC-096 |
| `ended_at` | timestamptz | 可空 | `(derived)` |

`playback_session_id + client_instance_id` 唯一；每个 session/client 只有一行，可续期或结束。
有效租约定义为 `ended_at IS NULL AND expires_at > now()`；清理查询必须通过 session 的
`cache_job_id` 排除存在有效租约的缓存任务。

### 8.3 `movie_playback_state`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `movie_id` | UUID | 主键，每部影片唯一 | AC-111 |
| `position_seconds` | numeric(12,3) | 0..999999999.999 | AC-111/112 |
| `duration_seconds` | numeric(12,3) | 0..999999999.999，可空且非零 | AC-113 |
| `completed` | boolean | 95% 或剩余 < 120 秒 | AC-113 |
| `version` | bigint | 从 1 开始单调递增，expected-version CAS | `(derived)` |
| `last_watched_at` | timestamptz | 可空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | AC-111 |

TASK-111 的 0019 迁移创建本表。`movie_id` 外键级联删除影片本身，但不关联 cache/source/media/
subtitle/session，相关生命周期不得删除状态。position 非负；duration 只允许空或正数；version 至少
为 1；`completed=true` 时 position 固定为 0。请求 version 0 只创建首行，之后必须等于当前版本，
成功由服务端加 1。未知时长或 position 0 不完成；已知时长按 95% 或严格剩余 `<120` 秒完成。
产品不提供独立历史列表。

## 9. 事件、通知与诊断

### 9.1 `event_sequence`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `singleton_key` | boolean | 主键且恒为 true | AC-115/116 |
| `current_value` | bigint | 非负、事务内行锁递增 | AC-115/116 |

该单例行分配 `domain_event.sequence`。递增与领域写入、事件插入处于同一事务，事务回滚时不消耗水位。

### 9.2 `event_stream_version`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `stream` | varchar(64) | 联合主键，取值同 `domain_event.stream` | AC-115 |
| `aggregate_id` | UUID | 联合主键 | AC-115 |
| `current_version` | bigint | 正数、事务内递增 | AC-115 |

该表只保留聚合版本水位，不包含事件 payload。`domain_event` 到期清理后，后续事件仍从原 `stream_version` 继续递增。

### 9.3 `domain_event`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `event_id` | UUID | 主键 | NFR-003 |
| `sequence` | bigint | 数据库生成、全局单调、唯一 | AC-115/116 |
| `stream` | varchar(64) | `metadata/cache/credential/catalog/notification` | AC-115 |
| `aggregate_id` | UUID | 资源 ID | AC-115 |
| `stream_version` | bigint | 同聚合单调递增 | NFR-003 |
| `event_type` | varchar(128) | 版本化名称 | AC-115 |
| `payload` | jsonb | 脱敏任务快照 | AC-115/121 |
| `occurred_at` | timestamptz | 非空 | AC-115 |
| `expires_at` | timestamptz | 固定 `occurred_at + 30 days` | `(derived)` |

领域状态和事件必须在同一数据库事务提交。`event_id` 用于去重和外部游标句柄，`sequence` 用于全局追赶/快照水位，`stream_version` 用于聚合合并。客户端游标落后或事件缺失时使用同一事务水位下的有界 REST 快照。

### 9.4 `connection_test_result`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `target` | varchar(16) | 主键，`cloud115/javdb/dmm/gfriends/ai` | AC-119/121 |
| `status` | varchar(32) | `available/unavailable/credentials_invalid/not_configured` | AC-119/121 |
| `error_code` | varchar(128) | 可空、稳定错误码 | AC-121 |
| `elapsed_ms` | bigint | 非负 | AC-121 |
| `checked_at` | timestamptz | 非空 | AC-119/121 |

每个 target 只保留最近一次脱敏结果；秘密配置 replace/clear 后删除对应旧结果，避免把旧凭据的成功状态应用到新版本。

### 9.5 `notification`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `type` | enum | `cache_started/cache_ready/cache_failed/credential_expired` 等 | AC-117 |
| `resource_id` | UUID | 可空 | `(derived)` |
| `created_at` | timestamptz | 非空 | AC-117 |
| `read_at` | timestamptz | 可空 | `(derived)` |

通知保存精简事实，不建设通用活动中心或历史页面。客户端下次启动按未读通知和任务快照补拉。

## 10. 状态机

### 10.1 元数据任务

```text
queued -> running -> completed
                  -> completed_with_warnings
                  -> failed
```

合法规则：

- 只有管理员手动重试能从失败或 warning 事实派生新的 `queued` 行。
- `running` 超过 600 秒必须进入 `failed(metadata_timeout)`。
- worker 崩溃且 claim 过期后可恢复同一 `running` 行进行对账 `(derived)`，但不得把已明确失败行自动重跑。
- `completed_with_warnings` 表示核心成功、至少一个可选 stage 失败。
- `completed_with_warnings` 的富化重试只运行明确失败或缺失的可选 stage，原 job/stage 事实保持不可变。
- `failed + core_ready` 只有在当前 attempt 的 `javdb_core` stage 已 `succeeded` 时才可选择该 attempt 或父链中尚未成功的可选 stage；旧 attempt 留下的 `core_ready` 不能替当前失败的核心 stage 授权富化重试。

### 10.2 缓存任务

```text
queued -> submitting -> offlining -> resolving -> awaiting_selection -> ready
                     \-> submit_uncertain --(confirmed cancel/reconcile)--> cancelling
                                      resolving ---------------------> ready

queued/submitting/offlining/resolving -> cancelling -> cleaning -> cleaned
ready -------------------------------> cleaning -> cleaned
任一非终态 --------------------------> failed
cleaning ----------------------------> cleanup_failed
任何需要远端归属但证明失效的状态 ------> detached
```

状态分组：

| 分组 | 状态 | 用途 |
|---|---|---|
| 运行槽 | `submitting/offlining/submit_uncertain/resolving` | 固定最多 2 |
| 排队槽 | `queued` | 固定最多 10 |
| 就绪容量 | `awaiting_selection/ready/cleaning/cleanup_failed` | 清理成功前不释放 |
| 活动复用 | 除 `failed/cleaned/detached` 外 | 同来源重复点击复用；不确定提交也不得重提 |
| 终态 | `failed/cleaned/detached` | 不再自动推进 |

持久 `capacity_class` 固定状态分组。`cancelling` 在安全清理完成前保留进入取消前的
queued/running/ready 类别，防止通过取消绕过上限；进入 `cleaning` 后归入 ready，只有终态
使用 released。`started` 是公开响应 disposition，不是持久状态。
`submit_uncertain` 不由自动 worker 领取；显式取消可重新进入 `cancelling` 做一次只读对账，
仍无远端证据时回到不确定状态。

### 10.3 影片进度

```text
new -> in_progress -> completed
completed -> in_progress (下次从头播放且产生新进度)
```

完成判断只使用服务端收到的可靠时长与位置。字幕、来源切换或缓存清理不删除影片进度。

## 11. 数据库不变量和索引

| 不变量 | 实现建议 | 来源 |
|---|---|---|
| 全局只有一个管理员 | 单例约束/引导锁 | AC-001 |
| 全局最多一个 115 绑定 | 固定 `singleton_key=true` 唯一约束 | REQ-001/AC-013 |
| 来源帖子幂等 | 唯一 `(website, external_post_id)` | AC-023/031 |
| 影片按番号唯一 | 唯一 `normalized_number` | AC-030 |
| 拒绝来源不可重建 | 同来源唯一拒绝 + 导入前 anti-join | AC-036 |
| 同番号一个活动元数据任务 | 部分唯一索引 | AC-037/040 |
| 元数据运行最多 3 | worker 槽位 + 监控不变量 | AC-038 |
| 同榜单/年份一个 current 快照 | normalized year 部分唯一索引 | AC-069/073 |
| 同榜单/年份一个活动同步请求 | normalized year 部分唯一索引 + claim fencing | AC-069/073 |
| 同来源一个活动缓存任务 | 部分唯一索引 | AC-091 |
| 播放请求 key 永久幂等 | `cache_play_request.idempotency_key` 主键 | AC-091 |
| 115 运行 2/排队 10 | advisory transaction lock + 事务计数 | AC-085 |
| 任务目录唯一 | `task_dir_cid` 唯一非空 | AC-080/081 |
| 清理不误删 | 归属证明检查 + 审计 | AC-081/098 |
| 影片进度唯一 | `movie_id` 主键 | AC-111 |
| 翻译不重复付费 | owner/source/model/prompt 唯一 + reserved/dispatched 持久 CAS | AC-057 |

搜索索引 `(derived)`:

- PostgreSQL 启用 `pg_trgm` 扩展。
- `resource_source(normalized_number, publish_date DESC)`。
- `movie(normalized_number)` 唯一 B-tree。
- `movie USING GIN (title_original gin_trgm_ops)` 和中文标题同类索引。
- `actor USING GIN (name_ja gin_trgm_ops)` 和中文名同类索引。
- `actor_alias USING GIN (normalized_alias gin_trgm_ops)`。
- `cache_job(status, created_at)`、`metadata_job(status, priority, created_at)`。
- `domain_event(sequence)`、`domain_event(event_id)` 和 `(stream, aggregate_id, stream_version)` 唯一；读取按 `sequence ASC`。

## 12. 保留与删除

| 数据 | 生命周期 |
|---|---|
| 影片、演员、关系、翻译、收藏、进度 | 永久，除非管理员显式删除产品数据 |
| AVdb 来源与同步游标 | 永久历史；全量缺失不自动删除 |
| 来源拒绝标记 | 永久 |
| 永久目录图片 | 永久，不随 115 缓存清理 |
| Actor Mapping/GFriends 快照 | 保留 current 文件及必要历史摘要；无数据库引用的 superseded 文件可维护清理 `(derived)` |
| GFriends URL 索引 | 随 current 快照全量原子替换，不保存图片字节 |
| 缓存任务审计 | 至少保留终态精简记录 `(derived)`；远端媒体定位清理后删除 |
| 就绪 115 内容 | 滑动 TTL/LRU，清理成功才释放 |
| 播放会话/租约 | 过期后可定期清除 `(derived)` |
| 事件 sequence/stream version 水位 | 永久精简计数，不保存 payload |
| 域事件正文 | 固定 30 天；每日只删除已过期行，状态由业务表恢复 |
| 客户端字幕副本 | 对应缓存、登录或本地 TTL 结束时删除 |

v1 不创建自动备份任务，也不提供旧 SakuraMedia Schema 迁移。
