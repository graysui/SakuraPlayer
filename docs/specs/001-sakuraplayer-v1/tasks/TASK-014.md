---
id: TASK-014
title: "后端基础与元数据端到端测试"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
reviewed_date: 2026-07-27
dependencies: [TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-012, TASK-013]
ac-mapping: [AC-001, AC-002, AC-004, AC-010, AC-018..AC-058, AC-063..AC-078, AC-115, AC-116, AC-119..AC-129, AC-133, AC-134, AC-132]
imp-requirements: [REQ-001, REQ-003, REQ-005..REQ-015, REQ-021..REQ-025]
cross-boundary: true
external-dependency-risk: true
provides: [backend metadata e2e suite]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-014: 后端基础与元数据端到端测试

**功能描述**: 使用 PostgreSQL、固定 AVdb/provider fixture 和 fake 外部适配器验证部署、认证、导入、元数据、目录、排行榜、事件和故障隔离全链路。

**规格映射**: TASK-001 至 TASK-013 已交付的 Phase 1 后端切片，以及 AC-023、AC-058、AC-132 的本阶段 E2E 观察点；逐项 `[IMP]` 证据仍由前序任务门禁所有

**E2E 边界**: [后端基础与元数据 E2E 契约](../contracts/backend-metadata-e2e.md)

## 验收条件

- [x] 从空 PostgreSQL 迁移后完成唯一管理员、AVdb 解密/六分类导入、首批任务、core_ready 目录、搜索、本地排行榜、事件快照和诊断查询。
- [x] 同一 Release/来源重复执行不产生重复记录；对应 `[SEF]` AC-023。
- [x] AI 不可用时 core_ready 影片仍可浏览；对应 `[SEF]` AC-058。
- [x] JavDB 以外的单个元数据源、AI 或 GFriends 故障不会清空已入库影片或排行榜快照；对应 `[SEF]` AC-132。
- [x] 缺失/错误 bootstrap token 被拒绝，正确 token 仅创建一次管理员；Compose Final 继续验证默认 loopback、四类密钥不复用、真实进程健康和重启恢复；对应 AC-133、AC-134。
- [x] `tests/e2e` 由唯一 Final runner 执行，测试不新增生产测试开关、Schema 或公开 API。

## Definition of Ready

- [x] TASK-001 至 TASK-013 均为 `completed` 且已有各自中文提交。
- [x] 自动 E2E 不需要真实 115、付费 AI 或 JavDB 写操作。
- [x] 既有固定 fixture 与确定性 fake handler 可覆盖成功、限流、结构变化、歧义和超时结果。

## 技术上下文

- 这是强制 E2E 任务，不实现新产品能力。
- 使用全新数据库、真实迁移和生产应用服务组合；外部适配器在既有构造边界注入 fake HTTP transport。
- API/worker/scheduler 的真实进程、重启和 ready 降级由同一次 Compose Final 覆盖，不在 pytest 内启动重复进程树。
- 测试结果按 AC ID 输出，`[SEF]` 只在此验证。

## 实现文件（仅文件名）

**创建**:

- `backend/tests/e2e/test_catalog_metadata_e2e.py` - 主链路。
- `backend/tests/e2e/test_metadata_failure_isolation_e2e.py` - AI/DMM/GFriends/图片故障隔离。
- `backend/tests/e2e/test_avdb_idempotency_e2e.py` - Release/来源幂等和拒绝。
- `backend/tests/e2e/conftest.py` - PostgreSQL、fake provider 和生产服务组合。

**修改**:

- `backend/tests/run-compose.ps1` - Final PostgreSQL 步骤收集 `tests/e2e`。
- `backend/tests/README.md` - 记录 E2E 分层入口和证据归属。

## 测试说明

**E2E 主流程**:

- 空库迁移 -> bootstrap -> 导入混合 AVdb 包 -> 90 天/5000 选择 -> 3 槽 worker -> core_ready -> 媒体库/搜索/女优/详情/排行榜。
- 从已持久化 `metadata_timeout` 事实手动重试，验证旧失败 attempt 保留且新 attempt 独立；真实 600 秒硬终止沿用 TASK-007 Final 证据。

**故障流程**:

- 主源失败/备用成功、摘要不一致、DMM/GFriends/AI/图片分别失败、JavDB 凭据未配置。
- WebSocket 断线、事件跳号、REST snapshot 恢复和日志秘密扫描。

**性能证据**:

- 289,858 来源导入与目录/搜索规模证据沿用 TASK-005/TASK-011 Final，排行榜 p95 沿用 TASK-012 Final；本任务不重复易抖动的大规模基准。

## Definition of Done

- [x] 本工作流 `[IMP]` 有自动证据。
- [x] AC-023、AC-058、AC-132 E2E 观察点通过。
- [x] 测试无真实付费/账号访问，报告无秘密。
- [x] Final runner 执行全部 E2E，完整 Compose、重启、降级恢复和资源清理通过。

## 验证证据

- Focused PostgreSQL E2E 最终为 `4 passed`；Fast 为 `466 passed, 8 deselected`，宿主 Docker 配置断言、秘密模式扫描和 `git diff --check` 通过。
- 只读审计修复了六分类证据不够直接和测试上下文 repr 可能暴露临时数据库密码的问题，修复后无剩余 P0/P1/P2。
- Compose Final 首次尝试通过：自包含 `466 passed, 8 deselected`，PostgreSQL integration/E2E `88 passed, 15 deselected`；迁移、五服务健康、认证 canary、秘密扫描、重启、ready 降级恢复和隔离资源清理全部完成。
- 正式评审见 [TASK-014--review.md](TASK-014--review.md)，结论为 `passed`。

**依赖**: TASK-001..TASK-013

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-014.md"`
