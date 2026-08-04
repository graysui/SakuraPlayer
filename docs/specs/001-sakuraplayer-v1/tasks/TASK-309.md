---
id: TASK-309
title: "HarmonyOS 播放请求与 60 秒全屏等待"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-307, TASK-308]
ac-mapping: [AC-084, AC-085, AC-086, AC-087, AC-088, AC-089, AC-090, AC-091, AC-117]
imp-requirements: [REQ-017, REQ-021]
cross-boundary: false
external-dependency-risk: false
provides: [HarmonyOS play request store, full-screen blocking wait, completion notifications]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-309: HarmonyOS 播放请求与 60 秒全屏等待

**功能描述**: 处理 play-request disposition，用 bindContentCover/全屏 NavDestination 锁定 started 任务最多 60 秒，支持二次确认取消、排队退出和后台通知。

**规格映射**: AC-084 至 AC-091、AC-117

## 验收条件

- [ ] 只有用户选来源点击播放才提交，重复点击复用；对应 AC-084、AC-091。
- [ ] started 全屏锁定，普通返回/Tab/搜索不可操作，只有二次确认取消；60 秒内 ready 自动播放；对应 AC-086、AC-087。
- [ ] 60 秒后退出等待并提示切换资源，后端继续；对应 AC-088。
- [ ] queued 立即退出且开始/完成不自动播放；后台完成只通知；对应 AC-089、AC-090、AC-117。
- [ ] 不提供 2/10 容量调整；对应 AC-085。

## Definition of Ready

- [ ] TASK-307 source ID、TASK-308 cache event/notification 可用。
- [ ] bindContentCover/openCustomDialog API 24 签名已核验，不用 deprecated CustomDialog。
- [ ] onBackPress/Navigation interception 行为通过 API 24 SDK 签名检查和自动化 UI fixture 验证。

## 技术上下文

- wait_deadline 来自服务端；本地计时只控制 UI，不写 failed。
- ready 自动导航只限当前 waiting job 且未过 deadline。
- 所有 timer/listener 在页面销毁取消，防止返回后突然导航。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/cache/PlayRequestStore.ets` - disposition/倒计时/事件。
- `harmony/entry/src/main/ets/features/cache/BlockingWaitPage.ets` - 全屏锁定。
- `harmony/entry/src/main/ets/features/cache/CancelDialog.ets` - 二次确认。
- `harmony/entry/src/ohosTest/ets/test/PlayRequestStore.test.ets` - 60 秒状态。
- `harmony/entry/src/ohosTest/ets/test/BlockingWaitPage.test.ets` - UiTest 返回/取消/导航锁。

## 测试说明

- ready、started 59 秒完成、60 秒退出后完成、queued、reused。
- 系统 back/Tab/搜索/前后台切换、确认取消和取消失败。
- 页面销毁后 timer/事件不会自动导航；完全退出任务继续后端。

## Definition of Done

- [ ] 播放请求、等待锁、60 秒、排队和通知完成。
- [ ] 无后台预取或自动播放后台 ready。
- [ ] Hypium/UiTest 通过。

**依赖**: TASK-307, TASK-308

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-309.md"`
