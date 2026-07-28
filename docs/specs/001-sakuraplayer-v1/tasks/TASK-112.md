---
id: TASK-112
title: "缓存事件、通知、诊断与恢复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-103, TASK-104, TASK-105, TASK-106, TASK-107, TASK-108, TASK-109, TASK-110, TASK-111]
ac-mapping: [AC-115, AC-116, AC-117, AC-118, AC-119, AC-121, AC-122, AC-127]
imp-requirements: [REQ-021, REQ-022, REQ-023]
cross-boundary: true
external-dependency-risk: false
provides: [cache events, notifications, snapshots, cache admin API, startup reconciliation]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-112: 缓存事件、通知、诊断与恢复

**功能描述**: 将缓存/凭据/播放状态接入持久事件和 REST 快照，提供计数角标、通知、任务操作、脱敏诊断和进程重启对账。

**规格映射**: AC-115 至 AC-122、AC-127

**冻结边界**: [TASK-112 缓存事件、通知与恢复确定性边界](../changes/2026-07-28--task-112-cache-events-recovery-contract.md)。

## 验收条件

- [x] 离线、缓存、凭据变化通过版本化事件推送，重连以 REST snapshot 恢复；对应 AC-115、AC-116。
- [x] 后台/运行中完成产生通知；完全退出不常驻，下次启动补拉；对应 AC-117。
- [x] 快照包含 queued/running/ready 角标数量；对应 AC-118。
- [x] 设置/诊断显示 TTL、115 状态、同步、stage/error/elapsed/attempt，并允许取消、清理和失败任务操作；对应 AC-119、AC-121、AC-122。
- [x] API/worker/PostgreSQL 健康，重启后缓存状态与 115 对账；对应 AC-127。

## Definition of Ready

- [x] TASK-013 全局 sequence、有界 snapshot 与 cache/credential 扩展端口和本工作流所有状态服务可用。
- [x] realtime-events.md 的 cache 事件、字段合并和 close code 已冻结。
- [x] 客户端不自动播放 ready 通知的产品规则明确。

## 技术上下文

- 事件 resource 是脱敏任务快照；60 秒结束无事件。TASK-112 复用 TASK-013 的全局 sequence、水位和 30 天保留，不另建游标体系。
- startup reconciliation 先锁 job 再查 remote/task directory，状态不能倒退。
- 操作 API 复用 TASK-104 cancellation 与 TASK-107 cleanup 业务用例，不在诊断路由直接改状态。
- TASK-104 只写持久状态；queued 开始、后台完成的版本化事件和通知由本任务统一发布。
- 0020 迁移创建 notification 并持久化 cleanup reason/failure stage；标记已读是幂等 REST 操作。
- 启动恢复复用 claim-fenced worker pipeline 做最多 100 次有界 drain；外部 I/O 不持有数据库行锁。
- 本任务不发布 playback 心跳/进度事件；worker/scheduler 无持久心跳时诊断继续为 unknown。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/events.py` - cache event publisher。
- `backend/src/sakuraplayer/cloud_cache/notifications.py` - 精简通知。
- `backend/src/sakuraplayer/cloud_cache/snapshot.py` - capacity/task 快照。
- `backend/src/sakuraplayer/cloud_cache/recovery.py` - 启动对账。
- `backend/alembic/versions/0020_cache_events_notifications.py` - notification、cleanup reason 与 failure stage。
- `backend/tests/integration/cloud_cache/test_cache_events_snapshot_api.py` - 断线补拉、未读通知、角标和不自动播放。
- `backend/tests/unit/cloud_cache/test_recovery.py` - 有界启动恢复控制器；既有 Fake115 集成集覆盖各状态接管。

## 测试说明

**单元测试**:

- event type/version/payload、角标分组、通知分类和脱敏。
- 状态恢复合法转换，不能从 ready 倒退到 offlining。

**集成测试**:

- API/worker 在 queued/offlining/resolving/ready/cleaning 崩溃重启，Fake 115 对账后状态正确。
- WebSocket 丢事件/关闭后 REST snapshot 恢复，ready 通知不自动创建 playback session。

**边界条件**:

- 游标过旧、完全退出后多任务完成、Cookie unavailable、取消/清理与恢复并发。

## Definition of Done

- [x] 事件、通知、角标、诊断、操作和恢复完成。
- [x] 重启不丢任务、不自动播放。
- [x] 快照/事件延迟目标有测试证据。

## 完成证据

- Fast 为 772 passed、8 deselected；Ruff format/lint、13 个 TASK-112 语义生产模块 mypy、
  宿主 Docker 配置、完整差异和只读审计通过，无剩余 P0/P1/P2。
- PostgreSQL 聚焦集 31 passed、1 deselected，覆盖事件与状态同事务、通知并发去重、未读补拉、
  角标、幂等已读、快照水位和有界恢复；ready 通知不会创建播放会话。
- Compose Final 首次尝试通过：自包含 771 passed、8 deselected，PostgreSQL
  integration/E2E 115 passed、16 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启、
  ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。

**依赖**: TASK-103..TASK-111

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-112.md"`
