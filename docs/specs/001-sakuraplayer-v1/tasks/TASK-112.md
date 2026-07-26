---
id: TASK-112
title: "缓存事件、通知、诊断与恢复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-103, TASK-104, TASK-105, TASK-106, TASK-107, TASK-108, TASK-109, TASK-110, TASK-111]
ac-mapping: [AC-115, AC-116, AC-117, AC-118, AC-119, AC-121, AC-122, AC-127]
imp-requirements: [REQ-021, REQ-022, REQ-023]
cross-boundary: false
external-dependency-risk: false
provides: [cache events, notifications, snapshots, cache admin API, startup reconciliation]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-112: 缓存事件、通知、诊断与恢复

**功能描述**: 将缓存/凭据/播放状态接入持久事件和 REST 快照，提供计数角标、通知、任务操作、脱敏诊断和进程重启对账。

**规格映射**: AC-115 至 AC-122、AC-127

## 验收条件

- [ ] 离线、缓存、凭据变化通过版本化事件推送，重连以 REST snapshot 恢复；对应 AC-115、AC-116。
- [ ] 后台/运行中完成产生通知；完全退出不常驻，下次启动补拉；对应 AC-117。
- [ ] 快照包含 queued/running/ready 角标数量；对应 AC-118。
- [ ] 设置/诊断显示 TTL、115 状态、同步、stage/error/elapsed/attempt，并允许取消、清理和失败任务操作；对应 AC-119、AC-121、AC-122。
- [ ] API/worker/PostgreSQL 健康，重启后缓存状态与 115 对账；对应 AC-127。

## Definition of Ready

- [ ] TASK-013 全局 sequence、有界 snapshot 与 cache/credential 扩展端口和本工作流所有状态服务可用。
- [ ] realtime-events.md 的 cache 事件和 close code 已冻结。
- [ ] 客户端不自动播放 ready 通知的产品规则明确。

## 技术上下文

- 事件 resource 是脱敏任务快照；60 秒结束无事件。TASK-112 复用 TASK-013 的全局 sequence、水位和 30 天保留，不另建游标体系。
- startup reconciliation 先锁 job 再查 remote/task directory，状态不能倒退。
- 操作 API 复用业务用例，不在诊断路由直接改状态。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/events.py` - cache event publisher。
- `backend/src/sakuraplayer/cloud_cache/notifications.py` - 精简通知。
- `backend/src/sakuraplayer/cloud_cache/snapshot.py` - capacity/task 快照。
- `backend/src/sakuraplayer/cloud_cache/recovery.py` - 启动对账。
- `backend/src/sakuraplayer/cloud_cache/admin_api.py` - cancel/cleanup/diagnostics/settings。
- `backend/tests/integration/cloud_cache/test_events_snapshot.py` - 断线补拉和角标。
- `backend/tests/integration/cloud_cache/test_recovery.py` - 各状态重启对账。

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

- [ ] 事件、通知、角标、诊断、操作和恢复完成。
- [ ] 重启不丢任务、不自动播放。
- [ ] 快照/事件延迟目标有测试证据。

**依赖**: TASK-103..TASK-111

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-112.md"`
