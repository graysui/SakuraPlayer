---
id: TASK-211
title: "字幕音轨倍速与影片进度"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-210, TASK-110, TASK-111]
ac-mapping: [AC-068, AC-107, AC-108, AC-109, AC-110, AC-111, AC-112, AC-113, AC-114]
imp-requirements: [REQ-013, REQ-020]
cross-boundary: false
external-dependency-risk: true
provides: [Windows subtitle cache, track controls, progress heartbeat]
---

# TASK-211: 字幕音轨倍速与影片进度

**功能描述**: 枚举内嵌字幕/音轨，下载 115 外置字幕到应用私有缓存，提供选择/倍速，并实现影片级自动续播、心跳和完成阈值。

**规格映射**: AC-068、AC-107 至 AC-114

## 外部依赖风险

- **依赖**: libmpv 内嵌 track、libass 和字幕文件编码。
- **状态**: MKV/ASS 字幕和轨道元数据随文件而异。
- **缓解**: media fixture、字幕失败隔离、私有缓存清理和 AC-130 真实样本。

## 验收条件

- [ ] 枚举内嵌字幕/音轨并提供字幕、音轨、倍速、全屏和进度控制；对应 AC-107、AC-114。
- [ ] 外置四格式下载到私有缓存，同名默认、多个切换，失败不阻止视频；对应 AC-108、AC-109。
- [ ] cache cleaned/logout/local expiry 删除对应字幕副本；对应 AC-110。
- [ ] 跨端影片进度自动续播，无选择框；95%/剩余 2 分钟完成且下次从头；对应 AC-111 至 AC-113。
- [ ] 详情和播放按钮状态及时刷新；对应 AC-068。

## Definition of Ready

- [ ] TASK-210 Player/Controller、TASK-110 subtitle API、TASK-111 progress API 可用。
- [ ] 私有字幕目录命名只使用 server subtitle ID，不使用未清洗文件名路径。
- [ ] heartbeat/flush 周期和版本冲突处理确定。

## 技术上下文

- media_kit 使用 `SubtitleTrack.data` 或受控本地文件，不把鉴权 URL 长期交 mpv。
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

- [ ] 字幕/轨道/倍速/进度完整接入播放器。
- [ ] 私有字幕生命周期与登录/cache 事件一致。
- [ ] 无历史页面或续播选择框。

**依赖**: TASK-210, TASK-110, TASK-111

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-211.md"`
