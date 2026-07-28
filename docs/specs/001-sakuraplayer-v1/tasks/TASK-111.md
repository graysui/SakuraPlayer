---
id: TASK-111
title: "影片级进度与播放心跳"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-108]
ac-mapping: [AC-068, AC-111, AC-112, AC-113, AC-114]
imp-requirements: [REQ-013, REQ-020]
cross-boundary: false
external-dependency-risk: false
provides: [movie playback state, heartbeat API, completion rule]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-111: 影片级进度与播放心跳

**功能描述**: 保存跨端共享的影片级进度和播放租约心跳，自动续播，并按 95% 或剩余不足 2 分钟标记已看完。

**规格映射**: AC-068、AC-111 至 AC-114

**冻结边界**: [TASK-111 进度与心跳确定性边界](../changes/2026-07-28--task-111-progress-heartbeat-contract.md)。

## 验收条件

- [x] 进度关联 movie_id 而非临时媒体，Windows/HarmonyOS 读取同一状态；对应 AC-111。
- [x] 未完成进度自动续播，不提供“从头播放”选择框；对应 AC-112。
- [x] 达 95% 或剩余 < 120 秒时 completed，下次从头；对应 AC-113。
- [x] 详情/卡片/播放按钮可读取进度或已看完状态，播放器可上报标准控制产生的位置；对应 AC-068、AC-114。

## Definition of Ready

- [x] TASK-107 Lease 服务和 TASK-108 Session 行为可用；MoviePlaybackState 0019 迁移由本任务创建。
- [x] 心跳携带 client_instance_id，可选 expected-version progress 和 playing；独立 progress PUT 可 flush。
- [x] 服务端时钟、完成阈值、未知时长、CAS 冲突和 lease 结束语义已由变更规格冻结。

## 技术上下文

- 每部影片唯一状态；缓存换源/清理/字幕失败不删除进度。
- version 是 expected current version；首次 0，成功后服务端递增，冲突返回权威状态。
- 心跳刷新 lease 和 CacheJob TTL；无进度心跳合法，`playing=false` 可原子 flush 后结束 lease。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/playback/progress.py` - 影片进度和完成规则。
- `backend/src/sakuraplayer/playback/heartbeat.py` - lease/TTL/progress 原子更新。
- `backend/src/sakuraplayer/playback/progress_api.py` - progress/heartbeat 路由。
- `backend/tests/unit/playback/test_completion_rule.py` - 95%/120 秒边界。
- `backend/tests/integration/playback/test_cross_client_progress.py` - 乱序/跨端/换源。

## 测试说明

**单元测试**:

- 94.99%/95%、剩余 121/120/119 秒、未知时长、position 0 和 position 大于 duration。
- 首次 version 0、相等 version 更新、旧/未来 version 冲突及心跳事务回滚。
- completed 后 manifest 位置 0；新播放可重新进入 in_progress。

**集成测试**:

- Windows 写入后 HarmonyOS 读取，反向亦然；旧 version 请求不能回退进度。
- 换 source/cache、清理 ready、字幕失败后进度仍存在。

## Definition of Done

- [x] 影片级进度、自动续播、完成阈值和心跳完成。
- [x] 目录查询可显示进度/已看完。
- [x] 无观看历史列表 API。

## 完成证据

- Fast 为 759 passed、8 deselected；全仓 Ruff format/lint、5 个受影响播放生产模块 mypy、
  宿主 Docker 配置、完整差异和只读审计通过，无剩余 P0/P1/P2。
- PostgreSQL 集成覆盖跨 Windows/HarmonyOS 共享状态、旧版本冲突、缓存清理后保留状态，以及两个
  expected-version 0 并发事务只能成功一个；0019 迁移、数值特殊值和事务回滚均有自动证据。
- Compose Final 首次尝试通过：自包含 759 passed、8 deselected，PostgreSQL
  integration/E2E 115 passed、15 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启、
  ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。

**依赖**: TASK-108

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-111.md"`
