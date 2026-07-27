---
id: TASK-104
title: "离线提交、对账、取消与等待语义"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-103]
ac-mapping: [AC-084, AC-086, AC-087, AC-088, AC-089, AC-090, AC-091, AC-097]
imp-requirements: [REQ-017, REQ-018]
cross-boundary: false
external-dependency-risk: true
provides: [cache worker claim, offline submit reconcile poll cancel]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-104: 离线提交、对账、取消与等待语义

**功能描述**: worker 创建独立任务目录、提交/对账 115 离线、轮询状态、处理取消，并通过 API disposition 表达 started/queued/reused/ready 和 60 秒等待边界。

**规格映射**: AC-084、AC-086 至 AC-091、AC-097

## 外部依赖风险

- **依赖**: 115 mkdir、离线提交/列表/取消。
- **状态**: 非官方提交可能超时但已受理。
- **缓解**: 每任务目录、remote ID 分离、提交不确定先对账、不自动重复扣配额、Fake 故障编排。

## 验收条件

- [ ] 获得运行槽的任务返回最多 60 秒 wait_deadline，排队任务立即返回且开始/完成只通知不自动播放；对应 AC-086 至 AC-089。
- [ ] 60 秒未完成不标失败，任务继续后台执行；稍后 ready 只缓存并通知；对应 AC-088、AC-090。
- [ ] 取消需确认，运行任务可取消但不参加 TTL/LRU；对应 AC-086、AC-097。
- [ ] 重复播放请求不重复提交 115；对应 AC-091。

## Definition of Ready

- [ ] TASK-103 状态机/容量和 TASK-102 根目录可用。
- [ ] 提交不确定与取消错误码在 Cloud115Port 固定。
- [ ] 客户端 60 秒只是响应字段，不创建后端 timer 状态。

## 技术上下文

- worker `SKIP LOCKED` 领取，创建随机任务子目录后才解密 source 磁力提交。
- 远端 `info_hash` 与 CacheJob ID 分开保存；对账只使用类型化 `OfflineTaskPage`，不得依赖磁力/source URL 或 raw response。
- 取消固定 `delete_source_files=False`；not-found、invalid、quota、rate-limit、unavailable 与 submit-uncertain 按 Cloud115Port 稳定错误分别处理。
- 取消流程进入 cancelling，只有远端取消/安全清理确认后终结。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/worker/claim.py` - 运行槽领取和续租。
- `backend/src/sakuraplayer/cloud_cache/worker/offline.py` - mkdir/submit/reconcile/poll。
- `backend/src/sakuraplayer/cloud_cache/cancellation.py` - 二次确认和安全取消。
- `backend/src/sakuraplayer/cloud_cache/play_disposition.py` - started/queued/reused/ready 响应。
- `backend/tests/integration/cloud_cache/test_offline_worker.py` - 提交/轮询/对账。
- `backend/tests/integration/cloud_cache/test_wait_cancel.py` - 60 秒、排队和取消。

## 测试说明

**单元测试**:

- started 的 wait_deadline <= 60 秒，queued/reused/ready 的 deadline 为空。
- cancel 未确认拒绝，running 不被 TTL/LRU 选择。

**集成测试**:

- Fake 115 60 秒前完成自动可播、60 秒后完成只通知、queued 开始/完成不自动播放。
- 提交超时但远端已受理时对账复用；明确未受理不自动重提。

**边界条件**:

- cancel 与完成竞态、worker 重启、remote task 不存在、队列开始时客户端离线。

## Definition of Done

- [ ] 提交、对账、轮询、取消和等待语义完成。
- [ ] 60 秒结束不会写 failed。
- [ ] 无重复提交或自动播放后台完成任务。

**依赖**: TASK-103

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-104.md"`
