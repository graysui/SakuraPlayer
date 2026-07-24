---
id: TASK-213
title: "Windows 端到端与真实 115 门禁"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-201, TASK-202, TASK-203, TASK-204, TASK-205, TASK-206, TASK-207, TASK-208, TASK-209, TASK-210, TASK-211, TASK-212, TASK-113]
ac-mapping: [AC-005, AC-059..AC-122, AC-128, AC-129, AC-130, AC-132]
imp-requirements: [REQ-002, REQ-012..REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [Windows E2E suite, AC-130 real115 evidence]
---

# TASK-213: Windows 端到端与真实 115 门禁

**功能描述**: 先用 Fake 后端完成 Windows 用户旅程，再用真实 115 专用目录验证 AC-130；全部通过才允许 HarmonyOS 工作流进入。

**规格映射**: Windows/后端适用 `[IMP]`、AC-130 `[EXT]`、AC-132 `[SEF]`

## 外部依赖风险

- **依赖**: 真实 Windows 10/11、115 账号和单/多/分段/字幕样本。
- **状态**: 外部协议与媒体解码是发布关键风险。
- **缓解**: 专用 `SakuraPlayer-Cache` 测试目录、显式 marker、受控删除、脱敏证据和失败即阻断。

## 验收条件

- [ ] Fake E2E 完成登录、三导航、搜索、榜单、女优、详情、多来源、等待、播放器、字幕、进度、设置和清理。
- [ ] 真实 115 验证扫码、离线、原画、HLS 回退、Range seek、字幕下载和安全清理；对应 `[EXT]` AC-130。
- [ ] Windows 核心链路失败时不进入 HarmonyOS 功能开发；对应发布门禁。
- [ ] 单个可选元数据源故障不影响已有目录/榜单/播放；对应 `[SEF]` AC-132。

## Definition of Ready

- [ ] TASK-113 和 TASK-201 至 TASK-212 已实现并评审。
- [ ] 真实账号、测试来源和专属根目录由操作者确认。
- [ ] 测试不会接触根目录外任何用户文件。

## 技术上下文

- 真实 E2E 必须运行 release 产物或等价配置，不用 debug shortcut。
- Range seek 观察同 URL 并发和 403；HLS 验证最高 variant 与固定 UA。
- 清理后再查 parent/root，确认只删除任务目录。

## 实现文件（仅文件名）

**创建**:

- `windows/integration_test/windows_user_journey_test.dart` - Fake 全用户旅程。
- `windows/integration_test/windows_real115_e2e_test.dart` - AC-130 显式套件。
- `docs/acceptance/windows-real115-checklist.md` - 脱敏人工/自动证据表。

## 测试说明

**Fake E2E**:

- 两个窗口尺寸、浅深主题、加载/空/错误/重连、60 秒边界和后台通知。

**真实 115**:

- 扫码 -> 立即/排队 -> 单/多/分段文件 -> 原画 -> compatibility HLS -> 快速连续 seek -> srt/ASS -> 95%进度 -> active lease 拒绝清理 -> 退出后安全清理。
- 真实操作全程扫描日志/数据库，确认无 Cookie、磁力、完整上游/签名 URL。

## Definition of Done

- [ ] Fake Windows E2E 全部通过。
- [ ] AC-130 每项有脱敏证据且真实目录清理确认。
- [ ] HarmonyOS 进入门禁标记为 passed。

**依赖**: TASK-201..TASK-212, TASK-113

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-213.md"`
