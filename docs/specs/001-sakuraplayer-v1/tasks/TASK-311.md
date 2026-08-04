---
id: TASK-311
title: "HarmonyOS 字幕音轨进度与生命周期"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-310, TASK-110, TASK-111]
ac-mapping: [AC-068, AC-107, AC-108, AC-109, AC-110, AC-111, AC-112, AC-113, AC-114, AC-131]
imp-requirements: [REQ-013, REQ-020]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS subtitle cache, track controls, progress heartbeat]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-311: HarmonyOS 字幕音轨进度与生命周期

**功能描述**: 在 API 24 SDK 签名和 fixture 能力已验证前提下接入内嵌字幕/音轨、外置四格式私有缓存、字幕选择、倍速和影片级自动续播/完成阈值。

**规格映射**: AC-068、AC-107 至 AC-114、AC-131

## 外部依赖风险

- **依赖**: AVPlayer 的 track/external subtitle/MKV/ASS 能力。
- **状态**: ASS 与外置字幕是 AC-131 关键能力，不能假设全部 API 可用；物理真机不作为依赖。
- **缓解**: 安装 SDK 签名核验 + API 24 自动化 fixture；关键失败阻断，不调用外部播放器规避。

## 验收条件

- [ ] 枚举内嵌字幕/音轨并提供字幕、音轨、倍速、全屏、进度；对应 AC-107、AC-114。
- [ ] srt/ass/ssa/vtt 下载到 app cacheDir，同名优先、多个切换，失败不阻止视频；对应 AC-108、AC-109。
- [ ] cache cleaned/logout/local expiry 删除对应副本；对应 AC-110。
- [ ] 影片级进度跨端、自动续播无选择框、95%/2min 完成后从头；对应 AC-111 至 AC-113。
- [ ] 卡片/播放按钮状态更新；对应 AC-068。

## Definition of Ready

- [ ] TASK-310 API 24 fixture player checks 通过，TASK-110/111 后端契约可用。
- [ ] AC-131 已通过 SDK 签名和 fixture 证明 MKV + ASS；若缺少官方 external subtitle API 则阻断。
- [ ] cacheDir 文件名只使用 subtitle UUID，避免路径穿越。
- [x] heartbeat/flush 与 expected-version 冲突处理由 TASK-111 变更规格确定。

## 技术上下文

- Core File Kit 只操作 app cacheDir，不请求媒体库权限。
- 按 manifest 的 `cache_job_id` 保存映射；logout 204 清空全部字幕，`cache.job.cleaned.v1.resource.id` 清理对应 job，且不得晚于 `subtitle_cache_expires_at` 删除本地副本。
- heartbeat/flush 在 lifecycle 切换前完成；aboutToDisappear 不执行长 async，交 Store/Ability 协调。
- 所有 AVPlayer listeners 使用命名 callback 并 off。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/playback/TrackStore.ets` - 字幕/音轨/倍速。
- `harmony/entry/src/main/ets/features/playback/SubtitleCache.ets` - 下载/格式/删除。
- `harmony/entry/src/main/ets/features/playback/ProgressStore.ets` - resume/heartbeat/flush。
- `harmony/entry/src/ohosTest/ets/test/TrackStore.test.ets` - 轨道/失败隔离。
- `harmony/entry/src/ohosTest/ets/test/SubtitleCache.test.ets` - 路径/生命周期。
- `harmony/entry/src/ohosTest/ets/test/ProgressStore.test.ets` - 阈值/跨端版本。

## 测试说明

- 内嵌/外置/无字幕、多音轨、四格式、ASS 样本和字幕失败继续视频。
- logout/cache cleaned/local expiry/路径穿越名；永久图片不被删除。
- auto resume、乱序 version、95%/2min、完成后从头；前后台 flush。

## Definition of Done

- [ ] 字幕、轨道、倍速、进度和生命周期完成。
- [ ] 私有缓存无额外权限且 listener 无泄漏。
- [ ] 关键 AVPlayer 能力有 API 24 SDK 签名和自动化 fixture 证据，不要求真实设备证据。

**依赖**: TASK-310, TASK-110, TASK-111

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-311.md"`
