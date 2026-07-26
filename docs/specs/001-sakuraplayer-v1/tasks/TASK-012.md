---
id: TASK-012
title: "JavDB 排行榜快照"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-007, TASK-008, TASK-011]
ac-mapping: [AC-046, AC-069, AC-070, AC-071, AC-072, AC-073]
imp-requirements: [REQ-009, REQ-014]
cross-boundary: true
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

- [x] 页面查询只读本地 JavDB 快照，不在请求时抓上游；对应 AC-069。
- [x] 支持日/周/月/TOP250 和榜单适用年份；对应 AC-070。
- [x] 只展示有 AVdb 来源且 core_ready 的影片；对应 AC-071。
- [x] 有来源但未完成元数据时创建优先级 20 任务；对应 AC-072。
- [x] 同步失败保留最近成功快照；对应 AC-073。
- [x] TOP250 未配置凭据或目标榜单从未成功同步时返回 `ranking_snapshot_unavailable`，不伪造空成功快照；对应 AC-046、AC-073。

## Definition of Ready

- [x] TASK-007/008/011 已完成，JavDB provider、元数据 queue 和 MovieSummary 目录投影可用。
- [x] Ranking request/snapshot/entry 设计、迁移归属、board/year、游标和调度边界已由 [TASK-012 排行榜快照确定性与执行边界](../changes/2026-07-26--task-012-ranking-snapshot-boundaries.md) 冻结，0012 由本任务交付。
- [x] 可选登录凭据来自 TASK-003 secret provider，并由 TASK-008 单载荷凭据仓储读取。

## 跨边界说明

- Discovery 拥有排行榜请求、快照、条目、查询协调和 API。
- Catalog 只通过 TASK-011 安全批量 MovieSummary 端口与元数据 priority 20 端口发布能力；Discovery 不复制目录投影。
- scheduler 只入队，worker 执行 JavDB 网络同步。

## 技术上下文

- building 快照完整后原子切换 current；失败快照不影响 current。
- 条目可先只保存番号，查询时按 source/core_ready 过滤并保留原始 rank。
- TOP250 未配置账号时跳过需要登录目标；已有快照继续返回，从未有快照时返回稳定不可用错误，不影响其他榜单。
- 每天 01:45 Asia/Shanghai 入队；TOP250 支持总榜及 2008..当前年，历史年份有 current 后不重复日更。
- 游标绑定 immutable snapshot；重复番号保留首次和原 rank，空/全无效响应不切 current。

## 实施批次

| 批次 | 行为闭环 | 聚焦证据 |
|---|---|---|
| 1 | 正式契约、0012 Schema 与持久请求 queue | 迁移、状态形状、current/active 唯一、claim fencing |
| 2 | JavDB 四榜单与登录防腐适配器 | 固定 JSON fixture、年份、分页、空/重复/结构变化和脱敏 |
| 3 | 快照同步、原子切换与 metadata priority 20 | 失败保留、历史一次性、queued 提升/running/failed/并发 |
| 4 | Catalog 批量投影、snapshot cursor 与认证 API | MovieSummary、rank 间隙、503 reason、current 切换分页 |
| 5 | scheduler/worker 接线、Fast、审计、Final 与提交 | 完整门禁证据和一次中文提交 |

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/discovery/ranking_sync.py` - board/year 同步与快照切换。
- `backend/src/sakuraplayer/discovery/ranking_query.py` - 过滤后的游标查询。
- `backend/src/sakuraplayer/discovery/ranking_api.py` - `/rankings` 路由。
- `backend/src/sakuraplayer/scheduler/rankings.py` - 定时入队。
- `backend/src/sakuraplayer/worker/rankings.py` - claim/lease consumer。
- `backend/alembic/versions/0012_ranking_snapshots.py` - 请求、快照、条目和约束。
- `backend/tests/start/test_ranking_migration.py` - 0012 Schema 契约。
- `backend/tests/unit/discovery/test_ranking_sync.py` - 排名、登录和失败策略。
- `backend/tests/integration/discovery/test_ranking_api.py` - 过滤、任务入队和快照保留。
- `backend/tests/integration/start/test_ranking_postgres.py` - 0011/空库升级、约束和 downgrade。
- `backend/tests/unit/catalog/test_metadata_ranking_priority.py` - priority 20 提升、复用和失败边界。
- `backend/tests/unit/discovery/test_ranking_query.py` - snapshot cursor、本地投影和 503 reason。
- `backend/tests/unit/worker/test_rankings.py` - worker 心跳、完成和稳定失败码。

## 测试说明

**单元测试**:

- 日/周/月/TOP250/年份参数与原始 rank 顺序。
- 无凭据跳过 TOP250、无快照错误、同步失败/空响应时不误切 current。

**集成测试**:

- 混合无来源、raw-only、core_ready 条目，验证只返回目标影片并为 raw-only 创建 priority 20 任务。
- 成功快照后模拟上游失败，验证 API 继续返回旧 snapshot 和 synced_at。

**边界条件**:

- 历史年份首次同步、当前年刷新、榜单重复/非法番号、空响应、登录失败、claim 丢失和 current 翻页时切换。

## Definition of Done

- [x] 四类榜单、年份、快照切换和元数据联动完成。
- [x] 页面 API 无实时上游请求。
- [x] 失败保留测试通过。

## 验证证据

- 最终 Fast 为 450 passed、7 deselected；compileall、宿主 Docker 配置断言、OpenAPI strict YAML、敏感模式和 `git diff --check` 通过。
- PostgreSQL Fast 覆盖 0011/空库升级、current/active 唯一、downgrade/re-upgrade、并发 priority 20 和 250 条快照缓存查询；20 次查询 p95 小于 500 ms。
- Compose Final 尝试 1 通过：PostgreSQL/运行测试 83 passed、12 deselected，迁移、五服务健康、认证 canary、秘密扫描、重启、ready 降级恢复和隔离资源清理全部通过。

**依赖**: TASK-007, TASK-008, TASK-011

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-012.md"`
