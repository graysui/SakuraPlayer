---
id: TASK-012
title: "JavDB 排行榜快照"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-007, TASK-008]
ac-mapping: [AC-046, AC-069, AC-070, AC-071, AC-072, AC-073]
imp-requirements: [REQ-009, REQ-014]
cross-boundary: false
external-dependency-risk: true
provides: [ranking snapshot sync, ranking query API]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-012: JavDB 排行榜快照

**功能描述**: 定时同步 JavDB 日榜、周榜、月榜、TOP250 和适用年份为本地快照，缺元数据时排高优先级任务，失败保留最近成功快照。

**规格映射**: AC-046、AC-069 至 AC-073

## 外部依赖风险

- **依赖**: JavDB 排行榜与可选登录 TOP250。
- **状态**: 参考项目已验证榜单端点，账号/页面仍可能变化。
- **缓解**: 固定有序番号 fixture、快照原子切换、登录缺失跳过、上游失败不清空 current。

## 验收条件

- [ ] 页面查询只读本地 JavDB 快照，不在请求时抓上游；对应 AC-069。
- [ ] 支持日/周/月/TOP250 和榜单适用年份；对应 AC-070。
- [ ] 只展示有 AVdb 来源且 core_ready 的影片；对应 AC-071。
- [ ] 有来源但未完成元数据时创建优先级 20 任务；对应 AC-072。
- [ ] 同步失败保留最近成功快照；对应 AC-073。
- [ ] TOP250 未配置凭据或目标榜单从未成功同步时返回 `ranking_snapshot_unavailable`，不伪造空成功快照；对应 AC-046、AC-073。

## Definition of Ready

- [ ] TASK-008 JavDB provider 和 TASK-007 queue 可用。
- [ ] RankingSnapshot/Entry 迁移和 board/year 校验已确认。
- [ ] 可选登录凭据来自 TASK-003 secret provider。

## 技术上下文

- building 快照完整后原子切换 current；失败快照不影响 current。
- 条目可先只保存番号，查询时按 source/core_ready 过滤并保留原始 rank。
- TOP250 未配置账号时跳过需要登录目标；已有快照继续返回，从未有快照时返回稳定不可用错误，不影响其他榜单。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/discovery/ranking_sync.py` - board/year 同步与快照切换。
- `backend/src/sakuraplayer/discovery/ranking_query.py` - 过滤后的游标查询。
- `backend/src/sakuraplayer/discovery/ranking_api.py` - `/rankings` 路由。
- `backend/src/sakuraplayer/scheduler/rankings.py` - 定时入队。
- `backend/tests/unit/discovery/test_ranking_sync.py` - 排名、登录和失败策略。
- `backend/tests/integration/discovery/test_ranking_api.py` - 过滤、任务入队和快照保留。

## 测试说明

**单元测试**:

- 日/周/月/TOP250/年份参数与原始 rank 顺序。
- 无凭据跳过 TOP250、无快照错误、同步失败/空响应时不误切 current。

**集成测试**:

- 混合无来源、raw-only、core_ready 条目，验证只返回目标影片并为 raw-only 创建 priority 20 任务。
- 成功快照后模拟上游失败，验证 API 继续返回旧 snapshot 和 synced_at。

**边界条件**:

- 历史年份首次同步、当前年刷新、榜单重复番号、详情入库单条失败。

## Definition of Done

- [ ] 四类榜单、年份、快照切换和元数据联动完成。
- [ ] 页面 API 无实时上游请求。
- [ ] 失败保留测试通过。

**依赖**: TASK-007, TASK-008

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-012.md"`
