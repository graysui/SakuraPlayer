---
id: TASK-310
title: "AVPlayer 原画 HLS 固定 UA 与 seek"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-309, TASK-109]
ac-mapping: [AC-099, AC-100, AC-101, AC-102, AC-103, AC-104, AC-105, AC-106, AC-114]
imp-requirements: [REQ-019, REQ-020]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS AVPlayer surface, fixed UA transport, coalesced seek, playback modes]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-310: AVPlayer 原画 HLS 固定 UA 与 seek

**功能描述**: 使用 Media Kit AVPlayer + XComponent/Video surface 构建应用内播放器，在 API 24 已验证能力上设置固定 UA、跟随 302/Range/HLS，并串行合并 seek。

**规格映射**: AC-099 至 AC-106、AC-114

## 外部依赖风险

- **依赖**: API 24 AVPlayer 网络源对 custom UA、302、Range、HLS、MKV 的实际行为。
- **状态**: 这是 AC-131 的关键未知；技能文档不提供可假定的 custom-UA 签名。
- **缓解**: 必须从安装 SDK/官方样例核验 API，并先在真机探针通过；任一关键项失败停止任务，不发明 API。

## 验收条件

- [ ] 每次播放新建 12 小时 session，AVPlayer 请求使用固定 HarmonyOS UA 并跟随 `302 no-store`；对应 AC-099、AC-100、AC-102。
- [ ] 默认原画，取链失败/用户兼容播放使用 HLS，UI 只显示两模式；对应 AC-101、AC-103。
- [ ] 只使用应用内 AVPlayer，不提供外部播放器或时间轴缩略图；对应 AC-104、AC-106。
- [ ] seek 请求串行合并，标准进度/倍速/全屏控制可用；对应 AC-105、AC-114。

## Definition of Ready

- [ ] TASK-309 有 ready job，TASK-109 manifest 契约可用。
- [ ] AC-131 前置探针已证明 API 24 固定 UA、302、Range、HLS、MKV；否则阻断。
- [ ] AVPlayer/XComponent stateChange/error/seek API 从 SDK 6.1.1(24) 核验。

## 技术上下文

- listener 使用命名引用并在 release 前 off；状态按 initialized -> surfaceId -> prepare -> play。
- seek coordinator 一次只调用一个 AVPlayer.seek，中间目标覆盖为最后目标。
- 播放期间 keep screen on，退出恢复；不申请后台长时播放能力。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/playback/PlayerStore.ets` - session/mode/state。
- `harmony/entry/src/main/ets/features/playback/AVPlayerAdapter.ets` - Media Kit 生命周期/UA。
- `harmony/entry/src/main/ets/features/playback/SeekCoordinator.ets` - 串行合并。
- `harmony/entry/src/main/ets/features/playback/PlayerPage.ets` - XComponent/深色控制。
- `harmony/entry/src/ohosTest/ets/test/SeekCoordinator.test.ets` - 高频 seek。
- `harmony/entry/src/ohosTest/ets/test/PlayerStore.test.ets` - 模式/UA/生命周期。

## 测试说明

- 30-60 次连续 seek 首/末执行、错误清 pending；页面隐藏/销毁 release。
- original/compatibility 新 session、固定 UA、302/Range/HLS/MKV fixture 和过期重签。
- 无 external player/thumbnail route；播放器深色/横竖屏/全屏不重叠。

## Definition of Done

- [ ] AVPlayer、固定 UA、原画/HLS、seek 和控制完成。
- [ ] 所有网络/媒体 API 均来自 API 24 已验证签名。
- [ ] 真机探针失败时任务保持 blocked 而非降级绕过。

**依赖**: TASK-309, TASK-109

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-310.md"`
