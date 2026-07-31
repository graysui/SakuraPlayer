---
id: TASK-211
title: "字幕音轨倍速与影片进度"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-210, TASK-110, TASK-111]
ac-mapping: [AC-068, AC-107, AC-108, AC-109, AC-110, AC-111, AC-112, AC-113, AC-114]
imp-requirements: [REQ-013, REQ-020]
cross-boundary: false
external-dependency-risk: true
provides: [Windows subtitle cache, track controls, progress heartbeat]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-211: 字幕音轨倍速与影片进度

**功能描述**: 枚举内嵌字幕/音轨，下载 115 外置字幕到应用私有缓存，提供选择/倍速，并实现影片级自动续播、心跳和完成阈值。

**规格映射**: AC-068、AC-107 至 AC-114

## 外部依赖风险

- **依赖**: libmpv 内嵌 track、libass 和字幕文件编码。
- **状态**: MKV/ASS 字幕和轨道元数据随文件而异。
- **缓解**: media fixture、字幕失败隔离、私有缓存清理和 AC-130 真实样本。

## 验收条件

- [x] 枚举内嵌字幕/音轨并提供字幕、音轨、倍速、全屏和进度控制；对应 AC-107、AC-114。
- [x] 外置四格式下载到私有缓存，同名默认、多个切换，失败不阻止视频；对应 AC-108、AC-109。
- [x] cache cleaned/logout/local expiry 删除对应字幕副本；对应 AC-110。
- [x] 跨端影片进度自动续播，无选择框；95%/剩余 2 分钟完成且下次从头；对应 AC-111 至 AC-113。
- [x] 详情和播放按钮状态及时刷新；对应 AC-068。

## Definition of Ready

- [x] TASK-210 Player/Controller、TASK-110 subtitle API、TASK-111 progress API 可用。
- [x] 私有字幕目录命名只使用 server subtitle ID，不使用未清洗文件名路径。
- [x] heartbeat/flush 周期和 expected-version 冲突处理由 TASK-111 变更规格确定。

## 技术上下文

- media_kit 使用 `SubtitleTrack.data` 或受控本地文件，不把鉴权 URL 长期交 mpv。
- 按 manifest 的 `cache_job_id` 保存映射；logout 204 清空全部字幕，`cache.job.cleaned.v1.resource.id` 清理对应 job，且不得晚于 `subtitle_cache_expires_at` 删除本地副本。
- position 心跳默认 15 秒，暂停/退出/完成立即 flush。
- 本地字幕缓存与永久图片/GFriends 缓存分目录。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/playback/presentation/track_controller.dart` - subtitle/audio/speed。
- `windows/lib/features/playback/data/subtitle_cache.dart` - 下载、校验和清理。
- `windows/lib/features/playback/presentation/progress_controller.dart` - resume/heartbeat/flush。
- `windows/test/features/playback/track_controller_test.dart` - 多轨/字幕失败。
- `windows/test/features/playback/subtitle_cache_test.dart` - 生命周期/路径。
- `windows/test/features/playback/progress_controller_test.dart` - 跨端版本/完成阈值。

## 测试说明

- 内嵌/外置/无字幕、多音轨、ASS/srt/vtt/ssa、失败继续视频。
- logout/cache cleaned/本地 TTL 只删对应字幕，路径穿越文件名无效。
- resume 自动 seek、乱序 version、94.99/95%、121/119 秒和下次从头。

## Definition of Done

- [x] 字幕/轨道/倍速/进度完整接入播放器。
- [x] 私有字幕生命周期与登录/cache 事件一致。
- [x] 无历史页面或续播选择框。

## 实现证据

- `playback_api_test.dart` 覆盖字幕下载、影片进度、心跳、严格进度版本和 manifest 字幕授权集合；`subtitle_cache_test.dart` 覆盖四格式、8 MiB 上限、UUID 路径、复用、到期、cleaned job 和下载跨期隔离。
- `track_controller_test.dart` 与 `player_page_test.dart` 覆盖内嵌音轨/字幕、默认和手动外置字幕、失败隔离、陈旧 manifest 竞态及字幕/音轨/倍速/全屏/进度菜单调用。
- `progress_controller_test.dart` 与 `player_controller_test.dart` 覆盖自动续播、15 秒心跳、暂停/完成/退出 flush、CAS 冲突收敛、模式切换结束旧 lease 和乱序版本隔离；媒体库、详情、排行榜和女优页面消费即时权威进度。
- Final：89 个 Dart 文件格式无变化，`flutter analyze` 无问题，完整 `flutter test` 201 项通过，Windows debug build 通过并生成 `sakuraplayer_windows.exe`；未执行 TASK-212 release/安装包或 TASK-213 真实 115 门禁。

**依赖**: TASK-210, TASK-110, TASK-111

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-211.md"`
