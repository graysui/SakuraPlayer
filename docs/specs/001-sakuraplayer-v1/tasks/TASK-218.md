---
id: TASK-218
title: "元数据失败详情与队列开始暂停"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-207, TASK-208, TASK-215, TASK-216]
ac-mapping: [AC-066, AC-067, AC-121, AC-122]
imp-requirements: [REQ-013, REQ-022]
cross-boundary: true
external-dependency-risk: false
provides: [pending movie limited detail, persistent metadata queue control]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-218: 元数据失败详情与队列开始暂停

**功能描述**: 让搜索中的元数据排队、运行和失败影片可进入明确受限的详情页，并让管理员从诊断页暂停或恢复元数据新任务领取。

**实施边界**: [元数据失败详情与队列控制](../changes/2026-08-01--metadata-experience-controls.md)

## 验收条件

- [x] 搜索 pending DTO 返回 movie_id，Windows queued/running/failed 条目均可导航受限详情。
- [x] 非 core_ready 详情显式返回 metadata_state/error_code，只公开 active 来源和安全 AVdb 字段；正式列表可见性不变。
- [x] 受限详情显示中文状态且不允许收藏，来源选择和缓存/播放入口保持可用。
- [x] 管理员 pause 只阻止新 claim，不打断 running；resume 恢复领取且不创建或重试任务。
- [x] diagnostics 返回 metadata_paused，Windows 显示开始/暂停按钮并处理在途、成功刷新和失败状态。

## Definition of Ready

- [x] TASK-207、TASK-208、TASK-215、TASK-216 已完成。
- [x] 搜索、详情、诊断、元数据 claim 和 Windows 交互入口已核对。
- [x] Accepted Delta 已冻结受限详情和暂停事务语义。

## 实现批次

1. 搜索 pending movie_id、受限详情 API/DTO 与 Windows 导航/页面。
2. `metadata_worker_control` 迁移、队列控制服务/API/诊断与 Windows 开始暂停按钮。

## Definition of Done

- [x] Focused/Fast、PostgreSQL 锁测试、Windows analyze/test、只读审计和 Compose Final 全部通过。
- [x] OpenAPI、数据模型、目录/Windows 契约、追踪矩阵和交接同步。
- [x] TASK-217 与 TASK-214 保持 pending；热更新由下一独立任务处理。

**依赖**: TASK-207, TASK-208, TASK-215, TASK-216
