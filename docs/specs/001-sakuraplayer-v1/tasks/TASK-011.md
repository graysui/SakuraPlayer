---
id: TASK-011
title: "媒体库、搜索、详情与收藏 API"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-006, TASK-008, TASK-009, TASK-010]
ac-mapping: [AC-063, AC-064, AC-065, AC-066, AC-067, AC-068, AC-074, AC-075, AC-076, AC-077, AC-078]
imp-requirements: [REQ-013, REQ-015]
cross-boundary: true
external-dependency-risk: false
provides: [catalog discovery read ports, catalog REST API, global search, movie actor detail, favorites]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-011: 媒体库、搜索、详情与收藏 API

**功能描述**: 发布只读 core_ready 目录、组合筛选、全局搜索、补全占位、影片/女优聚合详情和单一收藏 API。

**规格映射**: AC-063 至 AC-068、AC-074 至 AC-078

## 验收条件

- [x] 媒体库返回去重影片，默认 AVdb 发布日期降序，支持六分类、字幕/破解/4K/有码、来源、可播放状态和大小筛选；对应 AC-063、AC-064。
- [x] 搜索支持番号、标题、演员姓名/别名并分组；命中 raw source 时入最高优先级任务并返回补全状态；对应 AC-065、AC-066。
- [x] 只有 core_ready 影片有正式卡片/详情，响应包含影片级进度或已看完状态；对应 AC-067、AC-068。
- [x] 影片详情和女优详情包含规格字段、多来源、写真与关联影片；对应 AC-074 至 AC-076。
- [x] 影片和女优只有单一收藏，并可分别用 `favorite=true` 分页查看；不提供多个播放列表或观看历史 API；对应 AC-077、AC-078。

## Definition of Ready

- [x] TASK-006/008/009/010 已完成，Movie/Actor/Source/Translation/Images 模型和既有 OpenAPI 可用。
- [x] `pg_trgm`、favorite、trigram 索引和游标归 TASK-011 的 0011 迁移与查询实现，边界已由 [TASK-011 目录查询与补全确定性边界](../changes/2026-07-26--task-011-catalog-query-boundaries.md) 冻结。
- [x] availability/progress 通过 [Catalog 与 Discovery 只读端口](../contracts/catalog-discovery-ports.md) 返回 Phase 1 空状态，后续 TASK-103/105/111 替换适配器。

## 跨边界说明

- 目录与元数据拥有 core_ready 聚合查询；发现只通过安全 DTO 消费，并拥有搜索协调和收藏。
- TASK-011 只提供 cache/playback 空端口，不提前创建 Phase 2 表或直接读取未来上下文内部模型。
- 搜索补全通过 MetadataCompletionPort 调用元数据队列，failed attempt 不自动重试。

## 技术上下文

- 聚合详情分批查询关系，避免多对多笛卡尔积。
- 编号精确查询优先 B-tree；标题/别名使用 trigram；limit 最大 100。
- 来源 DTO 不包含磁力或上游敏感字段。

## 实施批次

| 批次 | 行为闭环 | 聚焦证据 |
|---|---|---|
| 1 | 0011 pg_trgm/GIN/favorite Schema 与模型 | 空库/0010 升级、索引、唯一约束、SQLite 兼容 |
| 2 | 游标、空状态端口、媒体库/详情聚合 | 同来源筛选、稳定分页、core_ready、安全 DTO、100 上限 |
| 3 | 收藏 service/API | 目标可见性、PUT/DELETE 幂等、favorite=true 分页 |
| 4 | 搜索与 metadata queue 提升 | exact 优先、trigram、歧义、queued/running/failed、并发 |
| 5 | 真实规模性能、Fast、审计、Final 与同步 | NFR p95、完整门禁证据和一次中文提交 |

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/query_service.py` - 媒体库/详情聚合。
- `backend/src/sakuraplayer/discovery/search_service.py` - 全局搜索与补全入队。
- `backend/src/sakuraplayer/discovery/favorites.py` - 影片/演员单一收藏。
- `backend/src/sakuraplayer/discovery/models.py` - discovery 所有的 Favorite 模型。
- `backend/src/sakuraplayer/catalog/api.py` - movies/actors REST 路由。
- `backend/src/sakuraplayer/discovery/api.py` - search/favorite 路由。
- `backend/src/sakuraplayer/catalog/ports.py` - availability/progress/metadata completion 端口。
- `backend/alembic/versions/0011_catalog_discovery.py` - pg_trgm、搜索索引和 favorite。
- `backend/tests/start/test_catalog_discovery_migration.py` - 0011 Schema 契约。
- `backend/tests/integration/start/test_catalog_discovery_postgres.py` - 0010/空库升级、扩展和索引。
- `backend/tests/integration/catalog/test_catalog_api.py` - 筛选、可见性和聚合。
- `backend/tests/integration/catalog/test_catalog_performance.py` - 289,858 来源真实规模 p95 与 EXPLAIN。
- `backend/tests/integration/discovery/test_search_favorites.py` - 搜索/补全/收藏。
- `backend/tests/unit/catalog/test_catalog_api.py` - 认证、DTO 和筛选 API。
- `backend/tests/unit/catalog/test_catalog_query_service.py` - 筛选、游标、端口与聚合查询。
- `backend/tests/unit/catalog/test_metadata_search_priority.py` - 搜索队列提升和竞态。
- `backend/tests/unit/discovery/test_search_favorites.py` - 收藏、搜索分组和补全状态。

**修改**:

- `backend/alembic/env.py` - 注册 discovery 模型元数据。
- `backend/src/sakuraplayer/catalog/metadata_queue.py` - 搜索 queued 原子提升端口。
- `backend/src/sakuraplayer/api/app.py` - 认证目录/发现路由装配。
- `backend/src/sakuraplayer/api/__main__.py` - 生产组合根和受管图片根接线。
- `docs/specs/001-sakuraplayer-v1/contracts/rest-api.openapi.yaml` - 确定性查询与失败响应。

## 测试说明

**单元测试**:

- 验证分类/标签组合、默认排序、编号精确优先和别名搜索规范化。
- 验证 core_ready 过滤、无图片占位、多来源大小字段、单一收藏幂等和收藏集合分页。

**集成测试**:

- 同影片多个来源/演员/标签/图片时详情无重复行且无磁力字段。
- 搜索 raw-only 番号创建 priority 10 任务，完成后正式结果替换补全占位。

**边界条件**:

- 空结果、游标失效、超过最大 limit、actor 别名歧义、没有可播放缓存。

## Definition of Done

- [x] 媒体库、搜索、详情、女优和收藏契约实现。
- [x] 无历史页、自定义播放列表或年龄确认入口。
- [x] API 性能目标使用真实规模 fixture 验证。

## 验证证据

- Focused 收敛为 19 passed；最终 Fast 为 408 passed、7 deselected。
- Compose Final 尝试 4 通过：PostgreSQL/运行测试 78 passed、12 deselected，迁移、五服务健康、认证 canary、秘密扫描、重启、ready 降级恢复和隔离资源清理全部通过。
- 性能 fixture 含 289,858 条来源、5,000 部 core-ready 影片、1,000 位演员和 100,000 条别名；媒体库/演员列表、番号精确、标题和别名模糊搜索 p95 均通过 NFR-001，EXPLAIN 命中番号 B-tree、标题/别名 GIN 和来源 B-tree。

**依赖**: TASK-006, TASK-008, TASK-009, TASK-010

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-011.md"`
