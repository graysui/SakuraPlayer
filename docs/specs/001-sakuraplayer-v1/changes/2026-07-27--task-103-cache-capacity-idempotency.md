# Change Specification: TASK-103 缓存容量与幂等确定性边界

**Type**: Delta
**Date**: 2026-07-27
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-103 预审确认 2/10 容量、活动来源复用和公开播放请求已冻结，但原数据模型无法表达
`cancelling` 的原容量归属，单个 CacheJob 字段也无法保存“不同幂等键复用同一任务”的
全部请求事实。另有 Resources 来源读取端口、binding 解绑后的历史外键、媒体选择复数形状
和迁移归属未明确。直接实现会造成取消绕过容量、重复请求在终态后创建新任务，或跨上下文
直接读取磁力。本变更只补齐 AC-083 至 AC-085、AC-091 的确定性实施边界，不增加产品功能。

## ADDED

### 播放请求幂等事实

- 新增 `cache_play_request`，以全局唯一 `idempotency_key` 保存首次请求的 `movie_id`、
  `source_id` 和最终返回的 `cache_job_id`。单管理员产品不再增加 admin/client 作用域。
- key 只接受 16..128 个 ASCII 字母、数字、点、下划线、波浪号或连字符。
- 同 key、同 movie/source 永久返回原 CacheJob，包括任务已进入终态或 binding 已变化。
- 同 key、不同 movie/source 返回 `409 idempotency_conflict`，不得改写原请求事实。
- 不同 key 命中同一 source/binding 的活动任务时仍创建各自 `cache_play_request`，保证任一
  客户端随后重放自己的 key 都返回同一任务。

### 持久容量类别

- CacheJob 新增 `capacity_class=queued/running/ready/released`。
- `queued` 固定为 queued；`submitting/offlining/resolving` 固定为 running；
  `awaiting_selection/ready/cleaning/cleanup_failed` 固定为 ready；终态固定为 released。
- `cancelling` 保留进入取消前的 queued/running/ready 类别；转入 `cleaning` 后按 ready
  容量计数，只有 `cleaned/failed/detached` 才释放全部容量。
- 创建、复用、幂等映射和容量计数使用同一 PostgreSQL advisory transaction lock；生产
  不依赖 API 进程内锁。运行最多 2、排队最多 10；达到排队上限返回 `cache_queue_full`。
- 活动任务解绑 guard 获取同一容量锁后查询，避免与并发播放请求交错。
- 未绑定时播放请求返回 `cloud115_binding_required`；expired/unavailable/detached 分别沿用
  `cloud115_credentials_expired/cloud115_unavailable/cloud115_directory_not_found`。

### Resources 来源提交端口

- Resources 新增 `SourceSubmissionPort`。创建播放请求只调用 `validate_for_play`，在当前
  事务锁定并验证 source 属于 movie、状态为 identified/manual、磁力 envelope 完整且未拒绝。
- TASK-104 创建任务目录后才调用 `load_submission_payload`，在最小作用域解密磁力；明文
  字段必须 `repr=False`，不得进入 CacheJob、请求映射、日志、事件、错误或测试快照。
- Cloud Cache 不直接 import Resources ORM 或解密实现；端口的 SQLAlchemy 适配器由
  Resources 上下文拥有。`SourceRejectionPort` 的既有所有权与 TASK-106 调用边界不变。

## MODIFIED

- CacheJob `binding_id` 在活动状态必须非空；终态解绑后允许由 `ON DELETE SET NULL` 清除，
  `account_key` 与 `cache_root_cid` 快照永久保留。新绑定使用新 UUID，不复用旧 generation。
- 活动唯一索引固定为 `(source_id, binding_id)` 且只覆盖除
  `failed/cleaned/detached` 外的状态。
- `resolving` 属于运行态，因此允许进入 `cancelling`；取消仍由 TASK-104 实现。
- `started` 只属于 API disposition；新运行任务持久状态始终为 `submitting`。
- TASK-103 迁移只拥有 `cache_job` 与 `cache_play_request`。TASK-105 拥有
  `remote_media`、`remote_subtitle` 和有序 `cache_job_media_selection` 的迁移与约束。
- 多段媒体选择统一使用有序复数 `selected_media_ids`；删除 CacheJob 单值
  `selected_media_id`。TASK-103 返回空媒体集合，TASK-105 后填充。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| CacheJob / cache_play_request Schema | ADDED | HIGH |
| capacity transaction coordination | ADDED | HIGH |
| SourceSubmissionPort | ADDED | HIGH |
| play request/cache API | ADDED | MEDIUM |
| OpenAPI/data model/realtime event | MODIFIED | MEDIUM |

## Task Synchronization

本变更不创建或拆分正式任务。TASK-103 实现 CacheJob、请求幂等、容量、来源校验和当前
安全 API；TASK-104 消费磁力载荷并实现 worker/取消/60 秒等待；TASK-105 迁移并填充媒体、
字幕与有序选择。变更规格、契约、实现、测试、任务状态、追踪矩阵和交接进入 TASK-103
同一中文提交。

## Testing Strategy

- 领域单元测试覆盖每条合法转换、非法倒退、容量类别变化和 `wait_expired` 非状态。
- Schema 测试覆盖状态/容量形状、活动部分唯一索引、幂等唯一键、binding SET NULL 与
  迁移线性。
- PostgreSQL 并发测试覆盖 2 个 running、10 个 queued、queue full、同 key、不同 key 同
  source、payload 冲突、binding 解绑竞态和 `cancelling` 保留容量。
- API/安全测试拒绝跨影片、pending/rejected/missing magnet、额外 magnet 字段和未认证请求；
  响应、日志与数据库扫描不得出现磁力明文。
