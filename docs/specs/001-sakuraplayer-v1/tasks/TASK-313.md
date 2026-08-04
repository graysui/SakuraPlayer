---
id: TASK-313
title: "HarmonyOS 端到端验收"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-302, TASK-303, TASK-304, TASK-305, TASK-306, TASK-307, TASK-308, TASK-309, TASK-310, TASK-311, TASK-213]
ac-mapping: [AC-003, AC-059..AC-122, AC-128, AC-129, AC-132, AC-133..AC-135]
imp-requirements: [REQ-001, REQ-012..REQ-025]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS E2E suite, cross-platform state evidence]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-313: HarmonyOS 端到端验收

**功能描述**: 在 TASK-301 的 API 24 SDK/构建基线和全部鸿蒙功能任务完成后，使用 Fake 后端验证完整用户旅程、跨端状态一致性和可选服务故障隔离。

**规格映射**: HarmonyOS/后端适用 `[IMP]`、AC-003/132 `[SEF]`

## 外部依赖风险

- **依赖**: 已通过的 Windows 状态样本、API 24 SDK/构建基线和自动化 fixture。
- **状态**: 跨端一致性需要用同一服务端账号和固定快照验证，不能只比较页面截图。
- **缓解**: 默认套件使用 Fake 服务和固定快照；不连接物理真机或真实用户目录。

## 验收条件

- [ ] Fake E2E 完成登录、三导航、搜索、榜单、女优、详情、多来源、等待、播放器、字幕、进度、设置和清理。
- [ ] Windows 与 HarmonyOS 使用同一账号时目录、收藏、任务和播放进度一致；对应 `[SEF]` AC-003。
- [ ] 单个可选元数据源、AI 或 GFriends 故障不影响已有目录、排行榜快照和 115 播放；对应 `[SEF]` AC-132。
- [ ] TASK-301、TASK-310、TASK-311 的 AC-131 SDK 签名和 fixture 证据可查；若 SDK 或播放实现改变，必须重新执行受影响的自动化检查。
- [ ] 首次连接覆盖后端地址测试、bootstrap token、登录以及换地址后的 Asset Store/字幕/快照清理；对应 AC-133 至 AC-135。

## Definition of Ready

- [ ] TASK-213、TASK-302 至 TASK-311 已实现并评审，签名 HAP 构建产物可检查。
- [ ] AC-131 的 API 24 SDK/fixture 证据可查且没有关键失败。
- [ ] Windows 跨端状态 fixture 和 Fake 后端已准备，不要求 API 24 测试设备。

## 技术上下文

- 默认 CI 只执行 Fake Hypium/UiTest，不访问真实 115、JavDB 写操作或付费 AI。
- 使用同一 OpenAPI/事件 fixture 验证 Windows 与 HarmonyOS 的状态语义，不比较本地缓存路径。
- 自动化回归若发现固定 UA、302、Range、HLS、MKV 或 ASS 退化，重新打开 AC-131 相关实现阻断项。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/ohosTest/ets/test/HarmonyUserJourney.test.ets` - Fake 全用户旅程。
- `harmony/entry/src/ohosTest/ets/test/CrossPlatformState.test.ets` - 跨端状态一致性。
- `harmony/entry/src/ohosTest/ets/test/FailureIsolation.test.ets` - 可选服务故障隔离。
- `harmony/test/fixtures/cross_platform_state.json` - Windows/HarmonyOS 一致性固定样本。

## 测试说明

- 冷启动、登录、三 Tab、六分类、日/周/月/TOP250 与年度筛选、详情多来源、60 秒等待、字幕、续播、重连和诊断。
- 注入元数据源、AI、GFriends 单点故障，确认目录、排行榜和已就绪播放继续可用。
- 导入 Windows 状态 fixture 后验证目录、收藏、任务和进度语义一致；最后执行 AC-131 快速回归冒烟。

## Definition of Done

- [ ] Fake HarmonyOS E2E 全部通过，默认套件无真实外部访问。
- [ ] AC-003、AC-132 有跨端与故障隔离证据。
- [ ] AC-131 的 API 24 SDK/fixture 证据仍有效，HarmonyOS 完成门禁标记为 passed。

**依赖**: TASK-213, TASK-302..TASK-311

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-313.md"`
