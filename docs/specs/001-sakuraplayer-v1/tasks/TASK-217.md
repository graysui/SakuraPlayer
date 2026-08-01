---
id: TASK-217
title: "首次元数据快照启动修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-216]
ac-mapping: [AC-049, AC-069, AC-119, AC-121]
imp-requirements: [REQ-010, REQ-014, REQ-022]
cross-boundary: true
external-dependency-risk: true
provides: [initial provider snapshots, initial ranking snapshots]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-217: 首次元数据快照启动修复

**功能描述**: 让周中首次部署无需等待下一次周/日定时点即可幂等建立 Actor Mapping、GFriends 和排行榜持久请求。

**实施边界**: [外部元数据服务运行可用性](../changes/2026-08-01--provider-runtime-availability.md)

## 验收条件

- [ ] 没有任何 provider snapshot 持久事实时，scheduler 首次启动只排入一次请求。
- [ ] 没有任何 ranking 持久事实时，scheduler 首次启动只排入当前榜单目标。
- [ ] 重启、既有 queued/claimed/completed/failed 请求或 current snapshot 均不得触发自动重试。
- [ ] 后续周日 05:00 provider 与每日 01:45 排行榜调度保持不变。

## Definition of Ready

- [ ] TASK-216 已完成，JavDB 真实只读探测与核心 API 已恢复。
- [x] 正式数据库确认 provider snapshot 和 ranking request/snapshot 均为 0 条。
- [x] 首次启动幂等语义已由变更规格冻结。

## Definition of Done

- [ ] Focused/Fast/审计/Compose Final 全部通过。
- [ ] 正式环境只创建一次首次请求并建立可查询快照。
- [ ] TASK-214 保持 pending，完成后下一任务为 TASK-214。

**依赖**: TASK-216
