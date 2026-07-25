# Change Specification: AVdb 管线任务边界澄清

**Type**: Delta
**Date**: 2026-07-25
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-004 的下载、解密、调度和同步事实可以在来源 importer 之前独立交付，但原任务同时要求证明 `resource_source` 全量缺失不删除并让 worker 执行来源导入；`resource_source`、六分类过滤和 importer 又明确由 TASK-005 创建。为避免 TASK-004 越界实现 TASK-005 或以空 importer 伪造完成，本变更明确两项任务在 AVdb 管线中的生产者/消费者职责。产品行为、AC 文本、任务顺序和依赖保持不变。

## ADDED

### 管线生产者与消费者

**Requirements**:

- REQ-CHG-032: TASK-004 必须交付安全的 Release 下载/解密/行流、同步运行与失败事实、幂等调度请求和 worker consumer 端口；TASK-005 在来源 importer 可用后接通生产 worker consumer。
- REQ-CHG-033: AC-020/021 由 TASK-004 的上海时区调度生产者和 TASK-005 的来源导入消费者联合实现；任何单独停在 `queued` 的结果不得宣称每日或每周导入完成。
- REQ-CHG-034: AC-022 由 TASK-004 保证协调器不发布删除/失效指令，TASK-005 以真实 `resource_source` 仓储证明全量缺失不会删除或禁用既有来源。

**Acceptance Criteria**:

- [x] TASK-004、TASK-005、工作流索引和追踪矩阵明确联合所有权。
- [x] TASK-004 的完成证据不再要求尚不存在的来源表；TASK-005 增加 worker consumer 与全量保留证据。
- [x] AC-018 至 AC-024 的产品语义没有降低或删除。

## MODIFIED

- TASK-004 负责可被 worker 调用的消费端口和所有前置失败持久化，但不在来源 importer 存在前把调度请求标记为已导入。
- TASK-005 在实现六分类来源 importer 的同一任务中接通 claim、下载、解密、批量导入和 request 收尾。
- AC-020、AC-021、AC-022 的追踪从 TASK-004 单独实现改为 TASK-004 与 TASK-005 联合实现。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-004 | RESPONSIBILITY CLARIFICATION | MEDIUM |
| TASK-005 | RESPONSIBILITY CLARIFICATION | MEDIUM |
| 追踪矩阵 | MODIFIED | LOW |
| 产品规格与 AVdb 契约 | NONE | NONE |

## Testing Strategy

- TASK-004 验证安全行流、调度 cron、同槽幂等请求、运行/失败事实和 importer 端口无删除语义。
- TASK-005 使用隔离 PostgreSQL 验证 request claim、worker 执行、来源 upsert、重复 Release 和全量缺失保留。
- TASK-014 继续以 fake HTTP 端到端验证完整后端管线。

## Rollback Plan

若取消该边界澄清，必须先为 TASK-004 引入完整来源 importer 与 `resource_source` Schema，并同步删除 TASK-005 的重复职责；不得只回退追踪矩阵。
