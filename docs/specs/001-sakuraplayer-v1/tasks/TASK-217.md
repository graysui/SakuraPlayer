---
id: TASK-217
title: "首次元数据快照启动修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
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

**兼容边界**: [Actor Mapping blacklist 结构兼容](../changes/2026-08-01--actor-mapping-blacklist-compatibility.md)

## 验收条件

- [x] 没有任何 provider snapshot 持久事实时，scheduler 首次启动只排入一次请求。
- [x] 没有任何 ranking 持久事实时，scheduler 首次启动只排入当前榜单目标。
- [x] 重启、既有 queued/claimed/completed/failed 请求或 current snapshot 均不得触发自动重试。
- [x] 后续周日 05:00 provider 与每日 01:45 排行榜调度保持不变。

## Definition of Ready

- [x] TASK-216 已完成，JavDB 真实只读探测与核心 API 已恢复。
- [x] 正式数据库确认 provider snapshot 和 ranking request/snapshot 均为 0 条。
- [x] 首次启动幂等语义已由变更规格冻结。

## 实施批次

1. 以失败测试冻结 provider/ranking 首次请求、凭据分支和既有事实保护。
2. 在 PostgreSQL advisory transaction lock 下实现事务性首次排队并接入 scheduler composition root。
3. 修复真实 Actor Mapping 空 blacklist 结构兼容，保持条目白名单与 XXE 边界。
4. Focused、Fast、完整审计、Compose Final、正式环境验证、交接和中文提交。

## Definition of Done

- [x] Focused/Fast/审计/Compose Final 全部通过。
- [x] 正式环境只创建一次首次请求并建立可查询快照。
- [x] TASK-214 保持 pending，完成后下一任务为 TASK-214。

## 完成证据

- 修复后 Fast 为 821 passed、9 deselected；Ruff format/check、宿主 Docker 配置和 `git diff --check` 通过。
- Compose Final 尝试 2 通过 821 项自包含与 127 项 PostgreSQL integration/E2E，五服务健康、重启、ready 降级恢复和资源清理完成。
- 当前真实 Actor Mapping 8,598,215 bytes 可严格解析为 26,552 条 actor；空 `actor-blacklist` 被验证后忽略。
- 正式首次 provider 请求只创建 1 条；解析修复后保留历史失败事实并显式创建 1 条验证请求，最终 Actor Mapping/GFriends 各有 1 个 current。
- 正式 GFriends 关联为 839 个 profile、5,320 个 gallery；Actor Mapping 写入 3,697 条 mapping 别名和 715 条简介；四个 ranking 请求均 completed。

**依赖**: TASK-216
