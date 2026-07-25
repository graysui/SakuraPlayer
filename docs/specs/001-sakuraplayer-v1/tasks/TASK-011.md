---
id: TASK-011
title: "媒体库、搜索、详情与收藏 API"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-006, TASK-008, TASK-009, TASK-010]
ac-mapping: [AC-063, AC-064, AC-065, AC-066, AC-067, AC-068, AC-074, AC-075, AC-076, AC-077, AC-078]
imp-requirements: [REQ-013, REQ-015]
cross-boundary: false
external-dependency-risk: false
provides: [catalog REST API, global search, movie actor detail, favorites]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-011: 媒体库、搜索、详情与收藏 API

**功能描述**: 发布只读 core_ready 目录、组合筛选、全局搜索、补全占位、影片/女优聚合详情和单一收藏 API。

**规格映射**: AC-063 至 AC-068、AC-074 至 AC-078

## 验收条件

- [ ] 媒体库返回去重影片，默认 AVdb 发布日期降序，支持六分类、字幕/破解/4K/有码、来源、可播放状态和大小筛选；对应 AC-063、AC-064。
- [ ] 搜索支持番号、标题、演员姓名/别名并分组；命中 raw source 时入最高优先级任务并返回补全状态；对应 AC-065、AC-066。
- [ ] 只有 core_ready 影片有正式卡片/详情，响应包含影片级进度或已看完状态；对应 AC-067、AC-068。
- [ ] 影片详情和女优详情包含规格字段、多来源、写真与关联影片；对应 AC-074 至 AC-076。
- [ ] 影片和女优只有单一收藏，并可分别用 `favorite=true` 分页查看；不提供多个播放列表或观看历史 API；对应 AC-077、AC-078。

## Definition of Ready

- [ ] Movie/Actor/Source/Translation/Images 数据模型和 OpenAPI 已完成。
- [ ] `pg_trgm` 扩展和游标分页约定可用。
- [ ] 播放进度字段可先通过端口/空实现返回，后续 TASK-111 填充。

## 技术上下文

- 聚合详情分批查询关系，避免多对多笛卡尔积。
- 编号精确查询优先 B-tree；标题/别名使用 trigram；limit 最大 100。
- 来源 DTO 不包含磁力或上游敏感字段。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/query_service.py` - 媒体库/详情聚合。
- `backend/src/sakuraplayer/discovery/search_service.py` - 全局搜索与补全入队。
- `backend/src/sakuraplayer/discovery/favorites.py` - 影片/演员单一收藏。
- `backend/src/sakuraplayer/catalog/api.py` - movies/actors REST 路由。
- `backend/src/sakuraplayer/discovery/api.py` - search/favorite 路由。
- `backend/tests/integration/catalog/test_catalog_api.py` - 筛选、可见性和聚合。
- `backend/tests/integration/discovery/test_search_favorites.py` - 搜索/补全/收藏。

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

- [ ] 媒体库、搜索、详情、女优和收藏契约实现。
- [ ] 无历史页、自定义播放列表或年龄确认入口。
- [ ] API 性能目标使用真实规模 fixture 验证。

**依赖**: TASK-006, TASK-008, TASK-009, TASK-010

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-011.md"`
