---
id: TASK-210
title: "media_kit 原画 HLS 播放器"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-209, TASK-109]
ac-mapping: [AC-093, AC-099, AC-100, AC-101, AC-102, AC-103, AC-104, AC-105, AC-106, AC-114]
imp-requirements: [REQ-018, REQ-019, REQ-020]
cross-boundary: false
external-dependency-risk: true
provides: [Windows media selection, Windows media_kit player, fixed UA, throttled seek, playback modes]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-210: media_kit 原画 HLS 播放器

**功能描述**: 实现应用内 media_kit/libmpv 播放器、固定 Windows UA、12 小时 stream capability、原画/兼容模式和 Player 层 in-flight seek 合并。

**实施边界**: [TASK-210 Windows 播放器确定性边界](../changes/2026-07-31--task-210-windows-player-boundaries.md) 与 [Windows 播放器客户端契约](../contracts/windows-playback-client.md)。

**规格映射**: AC-093、AC-099 至 AC-106、AC-114

## 外部依赖风险

- **依赖**: media_kit/libmpv 与 115/CDN 的 302、Range、HLS 行为。
- **状态**: 同一 URL 并发 Range 过多可能 403。
- **缓解**: 固定 UA、`ThrottlingPlayer`、模式重新签发、Fake HTTP 和真实 AC-130 测试。

## 验收条件

- [ ] 每次打开播放器新建会话并使用固定 Windows UA 跟随 `302 no-store`；对应 AC-099、AC-100、AC-102。
- [ ] 原画默认；取链失败/用户选择兼容播放使用 HLS，菜单只显示两模式；对应 AC-101、AC-103。
- [ ] 歧义媒体按候选组提交完整有序选择，ready 缓存只在显式动作后播放；对应 AC-093。
- [ ] 只用应用内播放器，不生成时间轴缩略图；对应 AC-104、AC-106。
- [ ] 所有 seek 经 in-flight 合并，标准进度/倍速/全屏控制可用；对应 AC-105、AC-114。

## Definition of Ready

- [x] TASK-209 可获得完整 ready job，TASK-109 playback manifest 契约完成；job/首媒体 route 交接由 Windows 播放器客户端契约冻结。
- [x] media_kit 固定版本、libmpv UA header 配置和 error callbacks 已从本地解析依赖源码验证。
- [x] 不移植外部播放器和缩略图面板；候选选择与 TASK-211 边界已冻结。

## 技术上下文

- `ThrottlingPlayer` 覆盖 Player.seek，只保留最后 pending 目标。
- compatibility 重新 POST session，不复用 original 签名 URL。
- ready job 首媒体 ID 进入 typed route；完整有序队列以 manifest 为真相，所有 Media 使用固定 UA。
- awaiting-selection 按 candidate_id 选择完整有效分段组；后台 ready/通知不得自动播放。
- 播放器固定深色并保持稳定画面尺寸/控制栏。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/playback/data/playback_api.dart` - 严格 session/manifest DTO。
- `windows/lib/features/playback/presentation/throttling_player.dart` - seek 合并。
- `windows/lib/features/playback/presentation/player_controller.dart` - 会话/模式/错误。
- `windows/lib/features/playback/presentation/player_page.dart` - 深色播放器和标准控制。
- `windows/test/features/playback/throttling_player_test.dart` - in-flight 行为。
- `windows/test/features/playback/player_controller_test.dart` - 原画/HLS/UA/过期。
- `windows/test/features/playback/player_page_test.dart` - 控制、窄布局和无缩略图。

**修改**:

- `windows/lib/features/cache/data/cache_api.dart` - 媒体候选组选择 gateway。
- `windows/lib/features/cache/presentation/cache_page.dart` - awaiting-selection 与 ready 显式播放入口。
- `windows/test/features/cache/cache_page_test.dart` - 候选组选择与 ready 播放入口。

## 测试说明

- 30-60 次连续 seek 只执行首个和最后目标，错误清 pending；所有入口走同一 wrapper。
- original/compatibility 新 session、固定 UA、302、签名过期重开、no external player。
- awaiting-selection 完整候选组、ready job 首媒体、无效/陈旧 route 与后台不自动播放。
- 不存在 thumbnail API/UI；控制栏有进度/倍速/全屏并在窄窗口不溢出。

## Definition of Done

- [ ] 歧义候选选择与 ready 缓存显式播放闭环完成。
- [ ] media_kit、UA、原画/HLS、seek 和控制完成。
- [ ] 无外部播放器/缩略图代码。
- [ ] controller/player 测试通过。

**依赖**: TASK-209, TASK-109

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-210.md"`
