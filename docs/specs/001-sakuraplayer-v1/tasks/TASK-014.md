---
id: TASK-014
title: "后端基础与元数据端到端测试"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-012, TASK-013]
ac-mapping: [AC-001..AC-078, AC-115, AC-116, AC-119..AC-129, AC-023, AC-058, AC-132]
imp-requirements: [REQ-001..REQ-015, REQ-021..REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [backend metadata e2e suite]
---

# TASK-014: 后端基础与元数据端到端测试

**功能描述**: 使用 PostgreSQL、固定 AVdb/provider fixture 和 fake 外部适配器验证部署、认证、导入、元数据、目录、排行榜、事件和故障隔离全链路。

**规格映射**: 本工作流所有 `[IMP]`，以及 AC-023、AC-058、AC-132 的 E2E 观察点

## 验收条件

- [ ] 从空 PostgreSQL 启动后完成唯一管理员、AVdb 解密/六分类导入、首批任务、core_ready 目录和本地排行榜查询。
- [ ] 同一 Release/来源重复执行不产生重复记录；对应 `[SEF]` AC-023。
- [ ] AI 不可用时 core_ready 影片仍可浏览；对应 `[SEF]` AC-058。
- [ ] JavDB 以外的单个元数据源、AI 或 GFriends 故障不会清空已入库影片或排行榜快照；对应 `[SEF]` AC-132。

## Definition of Ready

- [ ] TASK-001 至 TASK-013 已实现并评审。
- [ ] 自动 E2E 不需要真实 115、付费 AI 或 JavDB 写操作。
- [ ] 外部 fixture 含成功、限流、结构变化、歧义和超时样本。

## 技术上下文

- 这是强制 E2E 任务，不实现新产品能力。
- 使用全新数据库、真实迁移、API/worker/scheduler 进程边界和 fake HTTP transports。
- 测试结果按 AC ID 输出，`[SEF]` 只在此验证。

## 实现文件（仅文件名）

**创建**:

- `backend/tests/e2e/test_catalog_metadata_e2e.py` - 主链路。
- `backend/tests/e2e/test_metadata_failure_isolation_e2e.py` - AI/DMM/GFriends/图片故障隔离。
- `backend/tests/e2e/test_avdb_idempotency_e2e.py` - Release/来源幂等和拒绝。
- `backend/tests/e2e/conftest.py` - PostgreSQL、fixture provider 和进程控制。

## 测试说明

**E2E 主流程**:

- 空库迁移 -> bootstrap -> 导入混合 AVdb 包 -> 90 天/5000 选择 -> 3 槽 worker -> core_ready -> 媒体库/搜索/女优/详情/排行榜。
- 手动重试一个 600 秒超时任务，验证旧失败 attempt 保留且新 attempt 独立。

**故障流程**:

- 主源失败/备用成功、摘要不一致、DMM/GFriends/AI/图片分别失败、JavDB 凭据未配置。
- WebSocket 断线、事件跳号、REST snapshot 恢复和日志秘密扫描。

**性能检查**:

- 在规格规模 fixture 上验证列表/搜索 p95 与分批导入内存边界。

## Definition of Done

- [ ] 本工作流 `[IMP]` 有自动证据。
- [ ] AC-023、AC-058、AC-132 E2E 观察点通过。
- [ ] 测试无真实付费/账号访问，报告无秘密。

**依赖**: TASK-001..TASK-013

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-014.md"`
