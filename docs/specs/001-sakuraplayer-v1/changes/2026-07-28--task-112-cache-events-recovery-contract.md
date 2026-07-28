# Change Specification: TASK-112 缓存事件、通知与恢复确定性边界

**Type**: Delta
**Date**: 2026-07-28
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-112 预审确认：事件基础设施已有 cache/credential/notification 扩展端口，但
`notification` 逻辑表没有迁移或已读协议；精简事件载荷与客户端整体替换算法冲突；CacheJob
没有清理原因，重启后无法区分 cancelled/cleaned；普通失败、启动逐状态恢复和跨边界写点也未
冻结。本变更补齐这些实施边界，不新增 playback 事件流、后台常驻客户端或跨进程健康心跳。

## ADDED

### 0020 Schema 与通知协议

- TASK-112 独占线性迁移 `0020_cache_events_notifications`。迁移创建 `notification`，并为
  CacheJob 增加可空 `cleanup_reason` 和 `failure_stage`。
- `notification` 保存 `id/type/resource_id/error_code/dedupe_key/created_at/read_at`；
  `dedupe_key` 唯一且不公开。cache 通知键固定绑定 `cache_job_id + type`；凭据过期键绑定
  `binding_id + credential_version + expired`，同一凭据版本重放不得产生重复通知。
- 通知类型固定为 `cache_started/cache_ready/cache_failed/credential_expired`。通知事实、
  `notification.created.v1` 和对应领域状态必须在同一事务提交。
- REST 快照只返回最新 100 条未读通知，按 `created_at DESC, id DESC`；任务快照仍是最终状态
  真相，超过通知上限不得丢失任务状态。
- 新增 `PUT /notifications/{notification_id}/read`。操作幂等，以服务端时钟设置首次 `read_at`，
  返回完整 Notification，并在首次修改时同事务发布 `notification.read.v1`；不存在返回
  `notification_not_found`。已读通知不再进入恢复快照。
- notification 与事件正文使用相同 30 天保留窗口；每日维护删除 `created_at <= now-30 days`
  的通知，不重置事件或聚合版本水位。

### Cache 事件与恢复快照

- cache publisher 通过显式端口注入 PlayRequest、claim/resolution、media selection、
  cancellation 和 cleanup 事务；禁止提交后补扫或 best-effort 发布。
- `cache.job.created/updated/selection_required/ready/failed/cancelled/cleaned/
  cleanup_failed/detached.v1` 的 resource 至少包含该时刻完整公开 CacheJob 字段；事件特有字段
  `disposition/rejected_source/cleanup_reason` 可追加。TASK-106 的确定性拒绝 failed 事件保持原
  事务和精简载荷，不回填、不重复发布；客户端按本变更的字段合并规则兼容。
- 普通 remote failed、无有效媒体及其他合法终态失败必须发布一个 `cache.job.failed.v1` 和一个
  幂等 `cache_failed` 通知；60 秒客户端等待结束仍不产生事件。
- queued 首次进入 submitting 时发布 `cache.job.updated.v1` 和 `cache_started` 通知。首次创建即
  started 的请求不另发 started 通知；ready 只通知且绝不创建 playback session 或自动播放。
- snapshot extension 在同一事务水位下返回最多 100 个 CacheJob：活动状态优先，其后最近终态；
  queued/running/ready 计数分别使用持久 capacity class，其中 ready 包含尚未安全释放的
  cleaning/cleanup_failed。
- credential publisher 在绑定、重扫、状态变化和解绑事务发布
  `credential.cloud115.changed.v1`；只有状态首次变为 expired 时创建当前凭据版本的过期通知。

### 清理原因与事件选择

- `cleanup_reason` 只允许 `cancelled/manual/ttl/capacity`。进入 cleaning 前必须持久化且后续重试
  保持不变；取消无远端副作用并直接 cleaned 时同样保存 `cancelled`。
- 自动选择同时满足 TTL 和容量时固定记为 `ttl`；只因容量超限时记为 `capacity`；管理 API 记
  `manual`；取消流程记 `cancelled`。
- 删除确认成功后，reason=cancelled 发布 `cache.job.cancelled.v1`，其余发布
  `cache.job.cleaned.v1`。cleanup_failed/detached 保留原 reason，确保重启和重试后事件类型稳定。

### 启动恢复矩阵

- worker 启动先执行最多 100 次的有界 cache recovery drain，随后进入常规消费循环；每次复用
  现有 offline/resolver/cleanup pipeline 的一个 `run_once`，遇到 idle 立即结束。
- queued/submitting/offlining/cancelling/resolving/cleaning 由现有领取器在短事务内锁行并以新
  owner/token/lease 接管；事务提交后才访问 115，写回必须再次匹配未过期 claim。不得在持有
  数据库行锁时执行外部 I/O。
- submitting 根据已持久化的 task directory、submit_started_at 和 remote info 继续既有幂等步骤；
  offlining 重新分页对账；cancelling 继续远端取消；resolving 重新枚举；cleaning 以新 attempt
  重新证明式删除。旧 token 永远不能写回。
- submit_uncertain 不自动领取或重提；awaiting_selection/ready 不在启动时远程降级；
  cleanup_failed 只由显式/维护 retry 重新进入 cleaning；failed/cleaned/detached 保持终态。
- 恢复产生的状态变化走同一事件 publisher。重复启动若无新状态变化，不产生重复事件或通知。

### 诊断与健康

- 诊断增加 cache capacity 计数及最近 cache failed/submit_uncertain/cleanup_failed/detached；普通
  cache attempt 为 1，cleanup 使用最新 `cache_cleanup_attempt.attempt_no`，elapsed 由持久时间
  计算，stage 使用 `failure_stage` 或 `cleaning`。
- 设置中的 115 状态优先投影当前 binding：active/expired/unavailable/detached 分别映射公开的
  available/credentials_invalid/unavailable/unavailable，并只返回稳定错误码。
- TASK-112 不创建 playback 事件或把 15 秒心跳写入 outbox。播放进度继续以 TASK-111 的 API、
  manifest 和目录投影为真相；playback 只为 lease guard 和诊断提供既有只读状态。
- 本任务不新增 scheduler/worker 持久心跳；没有证据时诊断继续返回 unknown。API/PostgreSQL
  直接探针、容器内 ready 和 Schema head 门禁保持运维健康契约不变。

## MODIFIED

### 客户端事件合并

- `resource` 是带 `id` 的类型化字段快照或安全字段补丁。客户端对同资源按字段浅合并；字段值为
  null 表示权威清空，数组字段出现时整体替换。
- 本地没有资源、sequence/stream version 跳号、未知事件版本或字段形状非法时拉 REST snapshot，
  不用不完整事件构造资源。该规则同时兼容既有 metadata 和 TASK-106 精简事件。

### 任务边界

TASK-112 改为跨边界应用聚合任务。它只能经显式事件/通知/快照端口接入现有领域事务；API 路由
继续复用 cancellation、cleanup、settings 和 diagnostics 应用服务，不直接修改状态机。

## Acceptance Criteria

- [x] notification 迁移、幂等、排序、30 天保留和已读协议已唯一确定。
- [x] cache/credential 事件事务写点、普通失败与 TASK-106 去重边界已唯一确定。
- [x] cancelled/cleaned 由持久 cleanup reason 决定，崩溃恢复后不丢语义。
- [x] 逐状态启动恢复、claim fencing、外部 I/O 生命周期和不倒退规则已唯一确定。
- [x] playback 范围和 worker/scheduler unknown 健康语义已明确。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| CacheJob / notification Schema | ADDED/MODIFIED | HIGH |
| cache/credential/notification event transactions | MODIFIED | HIGH |
| event snapshot / merge contract | MODIFIED | HIGH |
| startup worker recovery | ADDED | HIGH |
| settings / diagnostics / admin API | MODIFIED | MEDIUM |
| TASK-202/302 client event consumers | MODIFIED | MEDIUM |

## Testing Strategy

- 单元测试覆盖事件类型/载荷/脱敏、通知去重/已读/保留、cleanup reason 和恢复有界 drain。
- PostgreSQL 测试覆盖 0020 迁移、状态与事件/通知原子回滚、并发通知去重、snapshot 水位和
  expired claim 接管。
- Fake115 集成覆盖 submitting/offlining/cancelling/resolving/cleaning 崩溃恢复、普通失败、
  cancelled/cleaned、ready 不自动播放和重复启动幂等。
- Fast、完整差异审计和单次 Compose Final 按 `implementation-workflow.md` 执行；默认测试不访问
  真实 115。

## Rollback Plan

提交前整体回退 TASK-112 代码、测试、0020 迁移和本变更同步契约。提交后 notification 与
CacheJob 新字段只能以前向迁移演进；已确认的远端删除仍不可由数据库回滚恢复。

## Task Impact

不新增或拆分任务。TASK-112 实现本变更并同步功能规格、技术计划、数据模型、OpenAPI、实时
事件、TASK-202/302、追踪矩阵与交接；TASK-113 继续作为 Phase 2 E2E。
