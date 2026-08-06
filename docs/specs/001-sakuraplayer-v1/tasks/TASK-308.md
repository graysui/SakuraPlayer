---
id: TASK-308
title: "HarmonyOS 115 扫码缓存设置与诊断"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
completed-at: 2026-08-06
dependencies: [TASK-302, TASK-112]
ac-mapping: [AC-013, AC-016, AC-094, AC-118, AC-119, AC-120, AC-121, AC-122]
imp-requirements: [REQ-004, REQ-018, REQ-021, REQ-022]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS QR binding, cache page, settings diagnostics notifications]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-308: HarmonyOS 115 扫码缓存设置与诊断

**功能描述**: 实现 QR 绑定、缓存任务/角标、TTL 设置、连接测试、脱敏诊断、任务操作和 Notification Kit 完成通知。

**规格映射**: AC-013、AC-016、AC-094、AC-118 至 AC-122

## 外部依赖风险

- **依赖**: 115 QR 与 HarmonyOS Notification Kit 行为。
- **状态**: 进程后台/完全退出时能力不同。
- **缓解**: 后台仅在进程存活时发布本地通知；完全退出下次 snapshot 补拉，不申请常驻权限。

## 验收条件

- [x] QR 全状态和 credentials expired 重扫提示；对应 AC-013、AC-016。
- [x] 缓存任务/容量/角标、取消/清理/元数据手动重试；对应 AC-118、AC-122。
- [x] TTL 1 至 168 小时，默认 24；对应 AC-094。
- [x] 设置回显非敏感 JavDB/AI 现值、增量/全量同步状态，连接测试/严格诊断 DTO 脱敏，主密钥不可编辑；对应 AC-119 至 AC-121。
- [x] 管理员可对 warning 元数据任务选择失败/缺失富化阶段重试，不能选择 JavDB 核心或隐式重跑 AI；对应 AC-122。

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

- [x] QR、缓存、设置、诊断和通知完成。
- [x] 无常驻后台任务权限（进程存活期间投递本地通知，无常驻权限申请）。
- [x] Hypium/UiTest 通过。

**实现证据**: `QrBindingStore.ets`（2s 串行轮询/single-flight、confirmed 单次 confirm、
credentials_expired 与 unavailable 文案分离、PNG 只存内存、解绑二次确认）、`SettingsStore.ets`
（TTL 1..168 CAS replace/clear expected_version、state_conflict 重载、非秘密现值回显、
MGDB GitHub 仓库校验、连接测试 5 目标、全量同步）、`CacheStore.ets`（分页 24、容量 2/10/20
固定、取消 {confirmed:true} 202 替换、active_lease/ownership_mismatch）、`DiagnosticsStore.ets`
（paused 初始化、暂停/恢复单一布尔、富化重试 stages 白名单不含 javdb_core/默认不含 translation）、
`AppNotifications.ets`（Notification Kit 本地通知 + 显示后标记已读，无常驻权限）；
DTO 严格校验（枚举/上限/去重/负数/秘密字段只 configured）；ohosTest 模拟器实测 **151/151 全绿**，
debug/release HAP 构建 + `verify-app success`（API 24、INTERNET 唯一权限）。

**依赖**: TASK-302, TASK-112

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-308.md"`
