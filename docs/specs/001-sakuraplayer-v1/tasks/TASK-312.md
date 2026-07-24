---
id: TASK-312
title: "HarmonyOS API 24 真机前置门禁"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-301, TASK-213, TASK-214]
ac-mapping: [AC-006, AC-131]
imp-requirements: [REQ-002, REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [AC-131 API 24 real device evidence, HarmonyOS development gate marker]
---

# TASK-312: HarmonyOS API 24 真机前置门禁

**功能描述**: 在任何鸿蒙业务功能开发前，使用 TASK-301 的最小签名 HAP 和真实 API 24 设备验证固定 User-Agent、302、Range、HLS、MKV 与 ASS；任一关键项失败都阻断 TASK-302 及后续任务。

**规格映射**: AC-006、AC-131 `[EXT]`

## 外部依赖风险

- **依赖**: 已通过的 Windows 真实 115 门禁、DevEco 签名、真实 API 24 设备、115 账号及 MKV/HLS/ASS 样本。
- **状态**: Media Kit 的请求头、重定向、Range、容器和外挂字幕能力只能在目标 SDK 与设备上确认。
- **缓解**: 使用独立测试目录、显式 real-device marker 和脱敏协议证据；不以模拟器、推测 API 或兼容回退替代关键项。

## 验收条件

- [ ] TASK-213/AC-130 已通过且 Windows v1 门禁证据可查；对应 `[EXT]` AC-006。
- [ ] 已安装的 DevEco Studio、HarmonyOS SDK、Hvigor、ohpm 和 Node 精确匹配技术计划版本。
- [ ] 真实 API 24 设备逐项通过固定 User-Agent、302、Range、HLS、MKV 与 ASS；对应 `[EXT]` AC-131。
- [ ] 任一关键项失败时生成阻断报告，TASK-302 至 TASK-311 不得进入 `in_progress`。

## Definition of Ready

- [ ] TASK-213、TASK-214 和 TASK-301 已完成，最小签名 HAP 可侧载启动。
- [ ] 真实账号、专用缓存根目录和覆盖六个探针项目的样本已由操作者确认。
- [ ] 设备/账号 secret 只存在本地安全环境，日志和证据使用脱敏字段。

## 技术上下文

- 该任务是前置外部 E2E 门禁，不实现产品业务功能。
- 不臆造 AVPlayer 自定义 UA 或外部字幕 API；先在已安装 API 24 SDK 核对签名，再以真实设备行为定案。
- 测试使用 release HAP 或等价签名配置，302/Range 通过后端测试端点和脱敏访问日志确认。

## 实现文件（仅文件名）

**创建**:

- `harmony/probe/src/main/ets/pages/PlaybackProbe.ets` - 最小 AVPlayer/字幕探针页。
- `harmony/probe/src/ohosTest/ets/test/Api24PlaybackGate.test.ets` - 六项真机协议与媒体矩阵。
- `harmony/tool/run_api24_preflight.ps1` - 显式真机门禁入口。
- `docs/acceptance/harmonyos-api24-preflight.md` - 脱敏设备与结果证据表。

## 测试说明

- 固定 HarmonyOS 平台 User-Agent 请求原画，跟随后端 302，验证初始播放和连续 seek 的 Range 请求。
- 分别播放最高码率 compatibility HLS、MKV 原画和带 ASS 外挂字幕样本。
- 每项记录 pass/fail、稳定错误码、SDK/设备版本和脱敏证据；失败时不运行任何业务功能任务。

## Definition of Done

- [ ] AC-006、AC-131 每项有真实设备脱敏证据且无关键失败。
- [ ] `harmonyos-api24-preflight=passed` 门禁标记可供 TASK-302 DoR 校验。
- [ ] 失败报告能明确阻断后续任务，且不含账号、Cookie、签名 URL 或字幕正文。

**依赖**: TASK-213, TASK-214, TASK-301

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-312.md"`
