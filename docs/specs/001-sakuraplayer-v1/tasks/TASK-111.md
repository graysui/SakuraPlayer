---
id: TASK-111
title: "影片级进度与播放心跳"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
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

## 验收条件

- [ ] 进度关联 movie_id 而非临时媒体，Windows/HarmonyOS 读取同一状态；对应 AC-111。
- [ ] 未完成进度自动续播，不提供“从头播放”选择框；对应 AC-112。
- [ ] 达 95% 或剩余 < 120 秒时 completed，下次从头；对应 AC-113。
- [ ] 详情/卡片/播放按钮可读取进度或已看完状态，播放器可上报标准控制产生的位置；对应 AC-068、AC-114。

## Definition of Ready

- [ ] TASK-107 Lease 服务和 TASK-108 Session 行为可用，MoviePlaybackState 迁移存在。
- [ ] 心跳携带 client_instance_id、version、position/duration。
- [ ] 服务端时钟和完成阈值已冻结。

## 技术上下文

- 每部影片唯一状态；缓存换源/清理/字幕失败不删除进度。
- version 防止跨端乱序旧请求覆盖新位置。
- 心跳刷新 lease 和 CacheJob TTL；暂停/退出可单独 flush。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/playback/progress.py` - 影片进度和完成规则。
- `backend/src/sakuraplayer/playback/heartbeat.py` - lease/TTL/progress 原子更新。
- `backend/src/sakuraplayer/playback/progress_api.py` - progress/heartbeat 路由。
- `backend/tests/unit/playback/test_completion_rule.py` - 95%/120 秒边界。
- `backend/tests/integration/playback/test_cross_client_progress.py` - 乱序/跨端/换源。

## 测试说明

**单元测试**:

- 94.99%/95%、剩余 121/119 秒、未知时长和 position 0。
- completed 后 manifest 位置 0；新播放可重新进入 in_progress。

**集成测试**:

- Windows 写入后 HarmonyOS 读取，反向亦然；旧 version 请求不能回退进度。
- 换 source/cache、清理 ready、字幕失败后进度仍存在。

## Definition of Done

- [ ] 影片级进度、自动续播、完成阈值和心跳完成。
- [ ] 目录查询可显示进度/已看完。
- [ ] 无观看历史列表 API。

**依赖**: TASK-108

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-111.md"`
