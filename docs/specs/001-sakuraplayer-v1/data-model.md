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

用于 115 Cookie、AI key、可选 JavDB 凭据等可恢复秘密。JavDB 用户名和密码使用单个 `javdb.credentials` 加密 JSON envelope 原子 CAS，避免跨键混合版本。普通非敏感配置使用同一记录的 `public_value`，但同一键不能同时存在明文和密文。

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

**不变量**: 最多一条 `active` 绑定。Cookie 快照回写必须以 `credential_version` 为 CAS 条件，防止旧请求覆盖重新扫码。

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
| `attempt_count` | bigint | 从 0 单调递增 | `(derived)` |
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

### 6.1 `ranking_snapshot` 与 `ranking_entry`

`ranking_snapshot`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `board` | enum | `daily/weekly/monthly/top250` | AC-070 |
| `year` | smallint | 仅适用榜单可填 | AC-070 |
| `status` | enum | `building/current/superseded/failed` | AC-069/073 |
| `source_synced_at` | timestamptz | 上游快照时间 | AC-069 |
| `created_at` | timestamptz | 非空 | `(derived)` |

`ranking_entry`:

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `snapshot_id` | UUID | 外键 | AC-069 |
| `rank` | integer | 正数 | AC-069 |
| `normalized_number` | varchar(128) | 非空 | `(derived)` |
| `movie_id` | UUID | 可空，元数据完成后关联 | AC-071/072 |

主键 `(snapshot_id, rank)`。查询只输出 `movie_id` 有目标来源且影片 `core_ready` 的条目；缺元数据但有来源时入优先级 20 队列。新同步失败不改变 current 快照。

### 6.2 `favorite`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `target_type` | enum | `movie/actor` | AC-077 |
| `target_id` | UUID | 非空 | AC-077 |
| `created_at` | timestamptz | 非空 | `(derived)` |

唯一键 `(target_type, target_id)`。无列表名、排序和自定义播放列表实体。

## 7. 115 缓存

### 7.1 `cache_job`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `movie_id` | UUID | 外键 | AC-084 |
| `source_id` | UUID | 外键，只能来自 AVdb | AC-083/084 |
| `binding_id` | UUID | 外键 | AC-080 |
| `status` | enum | 见 10.2 | AC-085..098 |
| `idempotency_key` | varchar(128) | 客户端重复点击键 | AC-091 |
| `account_key` | varchar(128) | 创建时快照 | AC-080/081 |
| `cache_root_cid` | varchar(64) | 创建时快照 | AC-080/081 |
| `task_dir_cid` | varchar(64) | 提交前创建，可空 | AC-080/081 |
| `task_dir_name` | varchar(128) | 随机且不可由标题控制 | `(derived)` |
| `remote_info_hash` | varchar(128) | 115 远端任务 ID，可空 | `(derived)` |
| `remote_percent` | numeric(5,2) | 0..100 | `(derived)` |
| `selected_media_id` | UUID | 可空 | AC-093 |
| `ready_at` | timestamptz | 可空 | AC-094 |
| `last_accessed_at` | timestamptz | 可空 | AC-094/095 |
| `expires_at` | timestamptz | 可空 | AC-094 |
| `claim_owner` | varchar(128) | 可空 | `(derived)` |
| `claim_expires_at` | timestamptz | 可空 | `(derived)` |
| `failure_code` | varchar(128) | 可空 | AC-098/121 |
| `failure_detail` | text | 可空、脱敏 | AC-121 |
| `created_at` | timestamptz | 非空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | `(derived)` |

**索引和约束**:

- 同一 `source_id + binding_id` 最多一个活动状态任务，保证重复点击复用。
- 数据库事务保证运行态最多 2、`queued` 最多 10；状态分类见 10.2。
- `task_dir_cid` 非空时唯一。
- `ready` 必须有至少一个有效 `remote_media`，且 `selected_media_id` 属于本任务。
- 60 秒等待不保存为任务状态。

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
| `sequence_no` | integer | 分段顺序，默认 0 | AC-093 |
| `selection_score` | integer | 广告/样片/番号等评分 | `(derived)` |
| `is_valid` | boolean | 通过扩展名和排除规则 | AC-092 |
| `created_at` | timestamptz | 非空 | `(derived)` |

唯一键 `(cache_job_id, file_id)`。禁止保存原画/HLS URL。

### 7.3 `remote_subtitle`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `cache_job_id` | UUID | 外键 | AC-108 |
| `media_id` | UUID | 可空，同名匹配到具体视频 | AC-109 |
| `file_id` | varchar(64) | 115 文件 ID | `(derived)` |
| `pickcode` | varchar(128) | 字幕下载定位 | `(derived)` |
| `parent_cid` | varchar(64) | 受管目录内 | AC-108 |
| `name` | text | 文件名 | AC-108/109 |
| `extension` | enum | `srt/ass/ssa/vtt` | AC-108 |
| `size_bytes` | bigint | 下载上限检查 | `(derived)` |
| `match_score` | integer | 同名优先 | AC-109 |

数据库不保存字幕正文和客户端副本路径。

### 7.4 `cache_cleanup_attempt`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `cache_job_id` | UUID | 外键 | AC-098 |
| `attempt_no` | integer | 递增 | AC-098/121 |
| `ownership_evidence` | jsonb | 只含账号摘要和 CID，不含 Cookie | AC-081/098 |
| `status` | enum | `running/succeeded/failed/detached` | AC-098 |
| `failure_code` | varchar(128) | 可空 | AC-098 |
| `started_at` | timestamptz | 非空 | `(derived)` |
| `finished_at` | timestamptz | 可空 | `(derived)` |

## 8. 播放

### 8.1 `playback_session`

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

签名载荷包含 ID、owner/session epoch、模式、UA 摘要和过期时间。上游 URL 不保存。

### 8.2 `playback_lease`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `id` | UUID | 主键 | `(derived)` |
| `playback_session_id` | UUID | 唯一活动租约 | AC-096 |
| `client_instance_id` | UUID | 非空 | `(derived)` |
| `last_heartbeat_at` | timestamptz | 非空 | AC-096 |
| `expires_at` | timestamptz | 非空 | AC-096 |
| `ended_at` | timestamptz | 可空 | `(derived)` |

有效租约定义为 `ended_at IS NULL AND expires_at > now()`；清理查询必须排除存在有效租约的缓存任务。

### 8.3 `movie_playback_state`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `movie_id` | UUID | 主键，每部影片唯一 | AC-111 |
| `position_seconds` | numeric(12,3) | >= 0 | AC-111/112 |
| `duration_seconds` | numeric(12,3) | > 0，可空 | AC-113 |
| `completed` | boolean | 95% 或剩余 < 120 秒 | AC-113 |
| `version` | bigint | 单调递增，解决乱序 `(derived)` | `(derived)` |
| `last_watched_at` | timestamptz | 可空 | `(derived)` |
| `updated_at` | timestamptz | 非空 | AC-111 |

`completed=true` 时客户端下次从头；产品不提供独立历史列表。

## 9. 事件、通知与诊断

### 9.1 `domain_event`

| 字段 | 类型 | 规则 | 来源 |
|---|---|---|---|
| `event_id` | UUID | 主键 | NFR-003 |
| `stream` | varchar(64) | `metadata/cache/credential` | AC-115 |
| `aggregate_id` | UUID | 资源 ID | AC-115 |
| `stream_version` | bigint | 同聚合单调递增 | NFR-003 |
| `event_type` | varchar(128) | 版本化名称 | AC-115 |
| `payload` | jsonb | 脱敏任务快照 | AC-115/121 |
| `occurred_at` | timestamptz | 非空 | AC-115 |
| `expires_at` | timestamptz | 事件保留窗口 `(derived)` | `(derived)` |

领域状态和事件必须在同一数据库事务提交。客户端游标落后或事件缺失时使用 REST 快照。

### 9.2 `notification`

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
                                      resolving ---------------------> ready

queued/submitting/offlining -> cancelling -> cleaning -> cleaned
ready -------------------------------> cleaning -> cleaned
任一非终态 --------------------------> failed
cleaning ----------------------------> cleanup_failed
任何需要远端归属但证明失效的状态 ------> detached
```

状态分组：

| 分组 | 状态 | 用途 |
|---|---|---|
| 运行槽 | `submitting/offlining/resolving` | 固定最多 2 |
| 排队槽 | `queued` | 固定最多 10 |
| 就绪容量 | `awaiting_selection/ready/cleaning/cleanup_failed` | 清理成功前不释放 |
| 活动复用 | 除 `failed/cleaned/detached` 外 | 同来源重复点击复用 |
| 终态 | `failed/cleaned/detached` | 不再自动推进 |

`cancelling` 在安全清理完成前仍占原槽位或容量，防止通过取消绕过上限。

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
| 全局只有一个活动 115 绑定 | 部分唯一索引 | REQ-001/AC-013 |
| 来源帖子幂等 | 唯一 `(website, external_post_id)` | AC-023/031 |
| 影片按番号唯一 | 唯一 `normalized_number` | AC-030 |
| 拒绝来源不可重建 | 同来源唯一拒绝 + 导入前 anti-join | AC-036 |
| 同番号一个活动元数据任务 | 部分唯一索引 | AC-037/040 |
| 元数据运行最多 3 | worker 槽位 + 监控不变量 | AC-038 |
| 同来源一个活动缓存任务 | 部分唯一索引 | AC-091 |
| 115 运行 2/排队 10 | 事务计数或槽位行锁 | AC-085 |
| 任务目录唯一 | `task_dir_cid` 唯一非空 | AC-080/081 |
| 清理不误删 | 归属证明检查 + 审计 | AC-081/098 |
| 影片进度唯一 | `movie_id` 主键 | AC-111 |
| 翻译不重复付费 | owner/source/model/prompt 唯一 + reserved/dispatched 持久 CAS | AC-057 |

搜索索引 `(derived)`:

- `resource_source(normalized_number, publish_date DESC)`。
- `movie(normalized_number)` 唯一 B-tree。
- `movie USING GIN (title_original gin_trgm_ops)` 和中文标题同类索引。
- `actor_alias USING GIN (normalized_alias gin_trgm_ops)`。
- `cache_job(status, created_at)`、`metadata_job(status, priority, created_at)`。
- `domain_event(stream, event_id)` 和 `(aggregate_id, stream_version)` 唯一。

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
| 域事件 | 有限保留窗口 `(derived)`，状态由业务表恢复 |
| 客户端字幕副本 | 对应缓存、登录或本地 TTL 结束时删除 |

v1 不创建自动备份任务，也不提供旧 SakuraMedia Schema 迁移。
