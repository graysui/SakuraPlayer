---
id: TASK-103
title: "缓存任务状态机与 2/10 容量"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-102]
ac-mapping: [AC-083, AC-084, AC-085, AC-091]
imp-requirements: [REQ-017]
cross-boundary: false
external-dependency-risk: false
provides: [cache job aggregate, state machine, capacity slots, play request API]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-103: 缓存任务状态机与 2/10 容量

**功能描述**: 建立 CacheJob 聚合、合法状态转换、AVdb SourceId 播放请求、固定 2 个运行/10 个排队容量和重复点击复用。

**规格映射**: AC-083 至 AC-085、AC-091

## 验收条件

- [x] 播放请求只接受属于影片的 AVdb source_id，不提供其他磁力源或手动磁力；对应 AC-083。
- [x] 只有详情页选择来源并点击播放的用例能创建任务；对应 AC-084。
- [x] 运行固定最多 2、排队固定最多 10，用户不能调整；对应 AC-085。
- [x] 同来源重复点击复用 queued/running/ready 活动任务；对应 AC-091。

## Definition of Ready

- [x] TASK-102 binding/root、TASK-006 来源/拒绝事实和 TASK-003 SecretCipher 可用；
  TASK-103 新增的 [SourceSubmissionPort](../contracts/source-submission-port.md) 边界已冻结。
- [x] CacheJob 状态、容量类别、活动分组、迁移归属和部分唯一索引已由
  [TASK-103 确定性边界](../changes/2026-07-27--task-103-cache-capacity-idempotency.md) 确认。
- [x] Idempotency-Key 格式、全局作用域、冲突和终态重放契约已冻结。

## 技术上下文

- API 事务内先按 idempotency key 查重，再按 source/binding 查复用，最后在固定容量锁内
  创建 `submitting/queued`；`started` 只属于 API disposition。
- 客户端不能提交磁力正文；本任务只经 Resources 端口验证 source，TASK-104 提交前才获取
  最小作用域明文。
- `cancelling` 和 `cleanup_failed` 在确认清理前不提前释放容量。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/domain/cache_job.py` - 聚合和状态转换。
- `backend/src/sakuraplayer/cloud_cache/capacity.py` - 2/10 事务槽位。
- `backend/src/sakuraplayer/cloud_cache/play_request.py` - source 校验、复用和创建。
- `backend/src/sakuraplayer/cloud_cache/cache_api.py` - play-requests/cache-jobs 路由。
- `backend/src/sakuraplayer/catalog/cache_availability.py` - Catalog 来源可用性查询适配器。
- `backend/src/sakuraplayer/cloud_cache/models.py` - CacheJob 与播放请求幂等事实。
- `backend/src/sakuraplayer/resources/source_submission.py` - 来源验证与最小解密端口。
- `backend/alembic/versions/0015_cache_jobs.py` - CacheJob/请求事实迁移。
- `backend/tests/unit/cloud_cache/test_cache_state.py` - 合法/非法转换。
- `backend/tests/integration/cloud_cache/test_cache_capacity.py` - 并发 2/10 与幂等。
- `backend/tests/start/test_cache_job_migration.py` - Schema、索引与迁移归属。

## 测试说明

**单元测试**:

- 验证每条合法转换和非法状态倒退；wait_expired 不属于状态。
- 拒绝非 AVdb、跨影片 source、手动磁力字段和 rejected source。

**集成测试**:

- 并发创建超过 2/10，验证固定计数、queue_full 和无超卖。
- 重复 Idempotency-Key/source 点击返回同一 job，不能重复提交或占槽。

**边界条件**:

- 两客户端同时点击、ready 任务复用、cancelling 占槽、binding 变化。

## Definition of Done

- [x] 状态机、source 安全、容量和幂等完成。
- [x] 无可调整并发/排队设置。
- [x] 数据库并发测试通过。

## 实现证据

- Focused：缓存状态、来源、API 与迁移静态测试 89 passed。
- Fast：Ruff format/lint、5 个新增模块 mypy 和宿主 Docker 断言通过；自包含回归
  596 passed、8 deselected；隔离 PostgreSQL 聚焦 17 passed。
- 完整差异审计修复 ORM 上下文边界和状态推进容量校验后，无剩余 P0/P1/P2。
- Compose Final：自包含 596 passed、8 deselected；PostgreSQL integration/E2E
  94 passed、15 deselected；迁移、健康、认证 canary、秘密扫描、重启、ready 降级恢复和
  隔离资源清理全部通过。

**依赖**: TASK-102

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-103.md"`
