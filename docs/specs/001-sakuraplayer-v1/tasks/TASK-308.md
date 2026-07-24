---
id: TASK-308
title: "HarmonyOS 115 扫码缓存设置与诊断"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-302, TASK-112]
ac-mapping: [AC-013, AC-016, AC-094, AC-118, AC-119, AC-120, AC-121, AC-122]
imp-requirements: [REQ-004, REQ-018, REQ-021, REQ-022]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS QR binding, cache page, settings diagnostics notifications]
---

# TASK-308: HarmonyOS 115 扫码缓存设置与诊断

**功能描述**: 实现 QR 绑定、缓存任务/角标、TTL 设置、连接测试、脱敏诊断、任务操作和 Notification Kit 完成通知。

**规格映射**: AC-013、AC-016、AC-094、AC-118 至 AC-122

## 外部依赖风险

- **依赖**: 115 QR 与 HarmonyOS Notification Kit 行为。
- **状态**: 进程后台/完全退出时能力不同。
- **缓解**: 后台仅在进程存活时发布本地通知；完全退出下次 snapshot 补拉，不申请常驻权限。

## 验收条件

- [ ] QR 全状态和 credentials expired 重扫提示；对应 AC-013、AC-016。
- [ ] 缓存任务/容量/角标、取消/清理/元数据手动重试；对应 AC-118、AC-122。
- [ ] TTL 1 至 168 小时，默认 24；对应 AC-094。
- [ ] 设置/连接测试/诊断脱敏，主密钥不可编辑；对应 AC-119 至 AC-121。

## Definition of Ready

- [ ] TASK-302 session/event 和 TASK-112 cache/settings API 可用。
- [ ] Notification Kit API 24 正式签名和授权行为已核验。
- [ ] 不申请 KEEP_BACKGROUND_RUNNING/dataTransfer。

## 技术上下文

- QR PNG 可由 ArrayBuffer/PixelMap 显示，会话完成释放。
- settings secret 输入不通过 AppStorage/PersistenceV2 保存。
- 2/10/3/600 固定值只读，无 Slider/Stepper 调整。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/settings/QrBindingStore.ets` - QR 状态。
- `harmony/entry/src/main/ets/features/settings/SettingsPage.ets` - 115/JavDB/AI/TTL。
- `harmony/entry/src/main/ets/features/cache/CachePage.ets` - 任务/容量/操作。
- `harmony/entry/src/main/ets/features/settings/DiagnosticsPage.ets` - 脱敏诊断。
- `harmony/entry/src/main/ets/core/notifications/AppNotifications.ets` - 本地通知。
- `harmony/entry/src/ohosTest/ets/test/SettingsCache.test.ets` - QR/TTL/任务/secret。

## 测试说明

- QR waiting/scanned/confirmed/expired/canceled、unavailable 区别、重绑冲突。
- TTL 边界、固定容量无编辑控件、取消确认/lease 清理拒绝。
- 后台进程存活通知、完全退出后重启 snapshot 补拉；HiLog/UI 无 secret。

## Definition of Done

- [ ] QR、缓存、设置、诊断和通知完成。
- [ ] 无常驻后台任务权限。
- [ ] Hypium/UiTest 通过。

**依赖**: TASK-302, TASK-112

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-308.md"`
