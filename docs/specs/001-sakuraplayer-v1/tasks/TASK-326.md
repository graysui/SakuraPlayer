---
id: TASK-326
title: "GFriends 女优资料恢复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-009, TASK-217, TASK-306, TASK-325]
ac-mapping: [AC-049, AC-050, AC-051, AC-052, AC-053]
imp-requirements: [REQ-010, REQ-CHG-318, REQ-CHG-319, REQ-CHG-320, REQ-CHG-321, REQ-CHG-322]
cross-boundary: true
external-dependency-risk: true
provides: [actor mapping verified enum compatibility, one-time provider snapshot repair, existing actor profile rebuild]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-326: GFriends 女优资料恢复

**功能描述**: 修复 GFriends 探活可用但女优映射为 unknown，以及既有女优没有中文简介、头像和写真的运行问题；现有 Docker 部署原地升级后自动补做一次安全快照重建。

**实施边界**: [TASK-326 GFriends 女优资料恢复](../changes/2026-08-06--task-326-gfriends-actor-profile-recovery.md)

## 验收条件

- [x] 真实上游观察到的 `verified="0"` 与既有 `verified="1"` 均可通过严格 Actor Mapping 解析，其他值和未知结构继续拒绝。
- [x] 旧数据库任一 current 快照缺失且没有活动请求时，升级迁移只补入一次 repair 请求；重复升级、已有活动请求或双 current 不重复入队。
- [x] repair 执行后既有唯一匹配 Actor 获得 Actor Mapping 中文名、简介和权威别名，GFriends profile/gallery 按现有安全 URL 规则重建。
- [x] 相同 GFriends 摘要也重新应用派生数据，修复首次快照发生在 Actor 入库前导致的空资产索引。
- [x] 原地升级保留 PostgreSQL、加密设置、影片、演员、收藏、已刮削关系、`data/`、`secrets/` 和永久目录图片。
- [x] 功能规格、元数据契约、任务索引、追踪矩阵、迁移和交接文档同步。

## Definition of Ready

- [x] TASK-009 已交付 Actor Mapping/GFriends 安全快照和唯一匹配。
- [x] TASK-217 已交付首次 provider snapshot 持久请求。
- [x] TASK-306 已交付女优列表、详情和 GFriends 图片消费。
- [x] TASK-325 已交付官方 Docker 镜像原地升级并保留持久数据。
- [x] 用户截图与真实固定上游只读取证已确认 `verified="0"` 导致整个 Actor Mapping 快照拒绝，GFriends 323,388 条索引可完整解析。
- [x] TASK-326 Delta 已冻结兼容值域、一次性 repair 和数据保留边界。

## 实现文件（仅文件名）

**后端与迁移**:

- `backend/src/sakuraplayer/catalog/actor_mapping.py`
- `backend/alembic/versions/0022_provider_snapshot_repair.py`
- `backend/tests/unit/catalog/test_actor_mapping.py`
- `backend/tests/unit/catalog/test_provider_snapshot_service.py`
- `backend/tests/start/test_provider_snapshot_repair_migration.py`
- `backend/tests/integration/catalog/test_actor_assets.py`

**规格**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-06--task-326-gfriends-actor-profile-recovery.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
- `docs/specs/001-sakuraplayer-v1/contracts/metadata-providers.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`

## Definition of Done

- [x] Actor Mapping、repair 迁移、相同摘要重建和 API 投影回归通过。
- [x] Focused、Fast、完整差异审计和 `git diff --check` 完成；用户已明确接受的既有 TASK-011 性能例外不要求重跑。
- [x] 任务状态、验收项、证据、交接和追踪矩阵在同一中文提交中更新。

## 验证证据

- Focused：Actor Mapping、provider snapshot service、迁移静态约束 30 passed；真实固定 Actor Mapping 解析 26,546 条；Ruff 与 compileall 通过。
- PostgreSQL：provider snapshot/actor assets 集成 7 passed，覆盖旧 failed 请求修复、活动请求/双 current 去重、相同摘要重建、原有 Actor/快照保留。
- Fast：后端自包含 `936 passed, 11 deselected`。
- 未重跑完整 Final 性能门禁；既有 TASK-011 影片列表 p95 性能例外按用户明确要求接受。未访问真实 GFriends 写操作、115、JavDB 写操作或付费 AI。

**依赖**: TASK-009, TASK-217, TASK-306, TASK-325
