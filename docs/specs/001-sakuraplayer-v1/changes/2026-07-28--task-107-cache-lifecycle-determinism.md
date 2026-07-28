# Change Specification: TASK-107 缓存生命周期确定性边界

**Type**: Delta
**Date**: 2026-07-28
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-107 预审确认，既有规格没有闭合异步安全删除下的 20 个容量语义、首次 TTL、
清理 attempt 恢复和 playback lease 外键归属。特别是 `playback_lease` 要求引用由 TASK-108
创建的 `playback_session`，而 TASK-108 又依赖 TASK-107，形成 Schema 依赖环。本变更冻结
最小持久结构、稳定选择和崩溃恢复规则，不把 TASK-108 的签名、会话创建或播放 API 提前实施。

## Change Summary

| Classification | Count |
|---|---:|
| ADDED | 3 |
| MODIFIED | 3 |
| REMOVED | 0 |

## ADDED

### 最小播放会话 Schema 归属

- TASK-107 创建完整 `playback_lease` 表及其外键所需的最小 `playback_session` 表。
- 最小会话表字段和约束遵循 `data-model.md`，但 TASK-107 不提供签名、会话创建、stream、
  原画/HLS 或公开播放 API。
- TASK-108 消费该 Schema 并独占播放会话业务行为；TASK-111 消费 TASK-107 的 lease service。

### 清理 attempt 与 claim fencing

- `(cache_job_id, attempt_no)` 唯一且 attempt_no 从 1 单调递增。
- attempt 状态为 `running/succeeded/failed/detached`；只有 running 的 finished_at 为空，终态必须
  有 finished_at；失败必须有稳定 failure_code，其余终态不得伪造失败。
- 清理领取复用 CacheJob 的 owner/token/expiry，所有完成写回校验未过期 token；同一任务最多一个
  活动清理执行者。
- 远端删除成功后进程崩溃时，下一次领取通过 directory not-found 收敛为 succeeded/cleaned。

### 本地媒体清除

- 远端删除成功或目录明确不存在后，同一事务先把 CacheJob 转为 `cleaned`，再删除该 job 的
  media selection、remote media 和 remote subtitle。
- 删除 remote media 级联删除其最小 playback session 和 lease；清理请求与 lease 获取共同锁定
  CacheJob，只有仍为 ready 才能新增或续期租约，关闭清理/心跳竞态。
- `detached` 和 `cleanup_failed` 不删除本地定位，也不释放 ready capacity。

## MODIFIED

### 20 个容量与稳定 LRU

**Previous Behavior**: `capacity_class=ready` 包含 `awaiting_selection/ready/cleaning/cleanup_failed`，
但规格只允许从 ready 选 LRU，也没有定义安全删除期间和无候选时的上限行为。

**New Behavior**:

- 20 是安全清理完成后的收敛目标，不是可以在远端删除确认前强制维持的瞬时硬上限。
- ready capacity 包含 `awaiting_selection/ready/cleaning/cleanup_failed` 以及保留 ready 类别的
  cancelling；只有 `awaiting_selection/ready` 可被自动选择，running 永不参与。
- TTL 到期优先于容量 LRU；稳定排序为
  `last_accessed_at NULLS FIRST, ready_at NULLS FIRST, created_at, id`。
- 有效租约、已领取项和清理状态排除；选择后在同一事务转为 cleaning 并写 claim/attempt。
- 如果只剩 lease、cleaning 或 cleanup_failed，允许容量暂时超过目标；失败继续占容量并可观察，
  不得虚假标记 cleaned。维护 worker 和手动 retry 使用同一清理器继续收敛。

### 滑动 TTL

**Previous Behavior**: 只描述 ready 的 24 小时滑动 TTL，未定义首次值、awaiting_selection、
设置变更和历史 NULL 行。

**New Behavior**:

- `awaiting_selection` 和 `ready` 都是 materialized cache；首次进入时由服务端时钟把
  `ready_at`、`last_accessed_at` 设为同一时间，并以当前 1..168 小时设置计算 expires_at。
- 成功创建播放会话才刷新 last_accessed_at/expires_at；失败访问不刷新。
- lease 获取/续期在同一 CacheJob 行锁事务中使用当前 TTL 设置刷新访问窗口，供 TASK-108 会话
  创建和 TASK-111 心跳直接复用。
- TTL 设置修改不批量改写已有缓存，只影响新 materialized cache 和下一次成功访问。
- 迁移前已存在的 materialized 行以 `COALESCE(last_accessed_at, ready_at, updated_at, created_at)`
  回填访问基准，并按迁移时默认 24 小时回填 expires_at；已有非空值保持不变。

### 证明式删除

**Previous Behavior**: 只要求验证账号、root、task、parent、owner，没有冻结检查顺序和 not-found。

**New Behavior**:

- 数据库先验证活动 binding id、account snapshot、root snapshot、task CID/name 和 job owner。
- 远端依次验证 root 仍为顶层 `SakuraPlayer-Cache`，task 仍是 root 的直接子目录且名称匹配。
- 任一归属不符转 `detached` 且不调用 delete；task 明确 not-found 视为删除已完成；root not-found
  或 binding 不一致属于 ownership mismatch，不追踪新位置。
- delete 只提交 task CID，`verified_parent_cid` 必须是已验证的 root CID；超时、限流、凭据和
  未知结果均转 cleanup_failed，等待显式/维护重试。

## Acceptance Criteria

- [x] 最小 playback session/lease Schema 不再形成 TASK-107/108 依赖环。
- [x] materialized cache 的首次 TTL、设置变更和历史回填已唯一确定。
- [x] 20 个容量在异步删除、有效租约和失败状态下有明确收敛语义。
- [x] cleanup claim、attempt、not-found 恢复和本地媒体删除事务已唯一确定。
- [x] running 任务和根目录外内容不会进入自动清理候选。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 功能规格 AC-094..098 | MODIFIED | MEDIUM |
| CacheJob/cleanup/playback Schema | ADDED/MODIFIED | HIGH |
| TTL/LRU/lease/ownership/cleanup service | ADDED | HIGH |
| TASK-107/108/111 边界 | MODIFIED | MEDIUM |
| Cache cleanup API/worker | MODIFIED | HIGH |

## Testing Strategy

- 单元测试覆盖 1/24/168 小时、首次/刷新、NULL/同时间稳定排序、租约和 running 排除。
- PostgreSQL 测试覆盖迁移、唯一 attempt、claim fencing、两个 worker、清理与心跳竞态。
- Fake 115 覆盖正常删除、task not-found、移动、root/account 变化、超时、崩溃后恢复和重试。
- 完整 Fast、只读审计与 Compose Final 按 `implementation-workflow.md` 执行。

## Rollback Plan

实现提交整体回退；未进入远端删除的 cleaning 可恢复原 materialized 状态。已经确认执行的远端删除
不可由数据库回滚恢复，因此清理调用前的完整归属证明、claim fencing 和 Fake 故障矩阵是发布门禁。

## Task Impact

不新增任务。现有 TASK-107 实现本变更；TASK-108/111 只同步消费边界。
