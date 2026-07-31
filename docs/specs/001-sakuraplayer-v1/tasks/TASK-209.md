---
id: TASK-209
title: "播放请求全屏等待与通知"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: in_progress
dependencies: [TASK-207, TASK-208]
ac-mapping: [AC-084, AC-085, AC-086, AC-087, AC-088, AC-089, AC-090, AC-091, AC-117]
imp-requirements: [REQ-017, REQ-021]
cross-boundary: false
external-dependency-risk: false
provides: [Windows play request controller, blocking wait page, cache notifications]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-209: 播放请求全屏等待与通知

**功能描述**: 从详情来源触发 play-request，处理 ready/started/queued/reused，started 时全屏锁定最多 60 秒，排队/超时/后台完成按规格退出和通知。

**实施边界**: [TASK-209 Windows 播放请求、等待与通知边界](../changes/2026-07-31--task-209-playback-wait-notification-boundaries.md)。

**规格映射**: AC-084 至 AC-091、AC-117

## 验收条件

- [ ] 只有用户选中具体 source 并点击播放才提交请求；重复点击复用；对应 AC-084、AC-091。
- [ ] started 进入全屏等待，除二次确认取消外不能操作其他页面；60 秒内 ready 自动进播放器；对应 AC-086、AC-087。
- [ ] 60 秒未完成退出等待提示切换资源，任务继续后台；对应 AC-088。
- [ ] queued 立即退出且开始/完成不自动播放；后台 ready 只通知并保留缓存；对应 AC-089、AC-090、AC-117。
- [ ] UI 不提供修改 2/10 固定容量；对应 AC-085。

## Definition of Ready

- [x] TASK-207 source selection、TASK-208 cache snapshot/event 可用；来源只输出 source_id，事件/快照已由前序任务交付。
- [x] PlayRequestResult disposition/wait_deadline 契约冻结；遵循 [Windows 播放请求客户端契约](../contracts/windows-play-request-client.md)。
- [x] 取消确认和窗口关闭行为明确；等待 route 只允许确认取消，窗口关闭不取消后台任务。
- [x] TASK-202 生命周期和 `AppNotificationSink` 端口可用；Windows 平台通知适配器依赖按 [ADR-004](../../adr/ADR-004-windows-cache-notifications.md) 冻结。

## 技术上下文

- 60 秒以服务端 wait_deadline 和单调本地倒计时显示，不能把超时写 failed。
- 全屏等待 route 阻止普通 back/导航；取消按钮打开确认 dialog。
- ready 事件只在当前仍等待同 job 且 deadline 内自动导航播放器。
- Windows toast 只展示 `cache_started/cache_ready/cache_failed/credential_expired`，点击进入缓存页，不自动播放；`flutter_local_notifications` 的 MSIX 历史通知限制不影响本任务。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/cache/presentation/play_request_controller.dart` - disposition/倒计时/事件。
- `windows/lib/features/cache/presentation/blocking_wait_page.dart` - 全屏锁定和进度。
- `windows/lib/features/cache/presentation/cache_notifications.dart` - 后台/前台完成通知。
- Windows 系统通知适配器由本任务接入 TASK-202 的通知投递端口，并拥有缓存文案与导航，依赖和边界见 ADR-004/Windows 播放请求客户端契约。
- `windows/test/features/cache/play_request_controller_test.dart` - 60 秒状态机。
- `windows/test/features/cache/blocking_wait_page_test.dart` - 导航锁/取消确认。

## 测试说明

- ready 直接播、started 59 秒 ready 自动播、60 秒后退出且稍后 ready 不自动播。
- queued/reused 状态、2/10 显示、重复点击同 job。
- back/侧栏/搜索/窗口导航在等待时不可操作，只有确认取消可离开。

## Definition of Done

- [ ] 播放请求、全屏等待、60 秒、排队和通知完成。
- [ ] 客户端不创建自动离线或后台预取。
- [ ] 状态/Widget 测试通过。

**依赖**: TASK-207, TASK-208

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-209.md"`
