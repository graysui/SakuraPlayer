# Change Specification: 元数据队列 DoR 迁移归属修正

**Type**: Delta
**Date**: 2026-07-25
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-007 的功能、数据模型和技术上下文都要求该任务创建 PostgreSQL 元数据队列，但原 Definition of Ready 又要求 `queued/running` 部分唯一约束和 claim expiry 已经迁移。TASK-001 至 TASK-006 均不拥有 `metadata_job`/`metadata_stage`，因此该条件会要求任务依赖一个没有正式所有者的预实现迁移。本变更只修正迁移归属和进入条件，不改变 AC-037 至 AC-043、AC-122、队列行为或任务依赖。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 0 |
| MODIFIED | 6 |
| REMOVED | 0 |

## ADDED

无。

## MODIFIED

### TASK-007 Schema 进入条件

**Previous Behavior**: TASK-007 开始实施前要求 `queued/running` 部分唯一约束和 claim expiry 已迁移，但没有任何前序任务拥有对应表或迁移。

**New Behavior**: TASK-007 开始实施前要求 `metadata_job`/`metadata_stage` 字段、活动任务部分唯一约束和 claim expiry 设计已经在数据模型中冻结；TASK-007 自身创建迁移、ORM 模型和 PostgreSQL 验证。

**Requirements**:

- REQ-CHG-043: 元数据队列表、活动 attempt 唯一约束和 claim 租约必须由 TASK-007 在同一任务提交中迁移、实现和验证，不得由未归属的临时实现预置。
- REQ-CHG-044: 迁移完成前不得把 TASK-007 标记为 `implemented`、`reviewed` 或 `completed`。

**Acceptance Criteria**:

- [ ] 全新数据库升级到 head 后存在 `metadata_job`、`metadata_stage`、活动 attempt 部分唯一索引和 claim expiry 字段。
- [ ] PostgreSQL 集成测试证明同一番号最多一条 `queued/running` attempt，终态行不阻止显式新 attempt。
- [ ] TASK-007 的任务、数据模型、迁移和测试在同一中文提交中交付。

**Impact**: TASK-007 Definition of Ready、后端任务索引和追踪矩阵说明；Breaking: NO，产品代码尚未实现。

### 持久化同优先级排序键

**Previous Behavior**: TASK-005 输出候选发布日期，技术计划要求同优先级按发布日期降序，但 `metadata_job` 数据模型没有保存该输入，重启后的稳定 claim 只能重新聚合可变化的来源表。

**New Behavior**: `metadata_job.sort_date` 保存创建 attempt 时 TASK-005 候选的发布日期；同优先级按该字段降序、空值最后，再按任务创建时间和 ID 升序。手动重试继承父任务的 `sort_date`。

**Requirements**:

- REQ-CHG-045: 元数据 attempt 必须持久化可空的 `sort_date`，重启或来源表后续更新不得改变既有 attempt 的队列顺序。

**Acceptance Criteria**:

- [ ] 同优先级任务按 `sort_date DESC NULLS LAST, created_at ASC, id ASC` claim。
- [ ] 完整重试和富化重试继承父任务排序日期，但优先级按管理员动作固定为 10。

**Impact**: `metadata_job` 数据模型和 TASK-007 队列测试；Breaking: NO，表尚未迁移。

### 首批入队恢复游标

**Previous Behavior**: TASK-005 提供 initial/history 候选，但没有持久化记录 TASK-007 是否已经完成首批分类；worker 重启可能把后续新增影片重新归入 initial。

**New Behavior**: `metadata_queue_state` 冻结首次 `initial_as_of`，分批写入最多 5000 个 initial，并在首批完成后持久化完成时间；此后所有未入队 raw 候选进入 history。未出现成功 AVdb sync 前不得提前完成首批。

### Provider 激活与子进程资源边界

**Previous Behavior**: TASK-007 需要 supervisor，但 TASK-008 才提供真实 JavDB/DMM/图片 executor。

**New Behavior**: worker 从 TASK-007 起轮询 seeder 和 supervisor。队列可持久入队；只有 `sakuraplayer.catalog.providers.runtime` 提供 TASK-008 executor 工厂后才领取 job。child CLI 只接收 job ID 与 claim owner，在子进程内重新创建 Engine、Session 和 http client，不共享父进程活动对象。后端 worker 只在 Linux 容器运行；父进程 watchdog 在异常死亡时终止完整 child 进程组。

### 崩溃阶段恢复

**Previous Behavior**: 恢复 full attempt 时可能重新运行已 succeeded 的 core 或 optional stage。

**New Behavior**: claim 返回持久化 pending stages 和既有 warning；child 只执行 pending，保留 succeeded/warning/skipped。过期 child 的普通写入被 fencing 拒绝，父进程终止其自有进程组后才可用 owner CAS 保存 timeout。

### 富化重试事实与可发现性

**Previous Behavior**: 只检查直接父 attempt 的 skipped 状态会扩大阶段范围；API 也无法显示真正可重试阶段。核心提交后超时的 failed attempt 只能完整重试。

**New Behavior**: 沿 `parent_job_id` 查找每个 optional stage 最近的非 skipped 事实，只允许 warning、failed 或符合核心提交条件的 pending stage。API 返回脱敏 stage 状态/错误码和 `retryable_stages`。`failed + core_ready` 仅在当前 attempt 的 `javdb_core` 已 `succeeded` 时可显式创建 missing_enrichment attempt；旧 attempt 遗留的 `core_ready` 不授权当前失败 attempt。未选择 translation 时不得调用付费 AI，完整 retry 入口仍保留。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-007 Definition of Ready | MODIFIED | LOW |
| Alembic / PostgreSQL metadata queue | OWNERSHIP CLARIFIED | MEDIUM |
| metadata_job 稳定排序键 | MODIFIED | LOW |
| metadata_queue_state 首批游标 | ADDED | MEDIUM |
| worker/child 激活 Port | MODIFIED | HIGH |
| 崩溃阶段恢复与 fencing | MODIFIED | HIGH |
| 富化 retry 链与 API 快照 | MODIFIED | HIGH |

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-007 的依赖或 AC 映射。迁移、模型、队列、supervisor、测试和契约同步仍由 TASK-007 一次完成。

## Testing Strategy

- 迁移结构测试检查表、约束、索引、外键和 downgrade 对称性。
- PostgreSQL 集成测试检查活动 attempt 唯一性、优先 claim、租约过期恢复和终态重试。
- Final 从全新数据库升级到 Alembic head，并执行完整 Compose 门禁。

## Rollback Plan

TASK-007 提交前可整体回退本变更和实现。提交后若迁移需要修正，必须新增前向迁移；不得删除终态 attempt 或通过手工 stamp 绕过 Schema 门禁。
