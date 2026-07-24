---
id: TASK-301
title: "API 24 Stage 工程与签名侧载基线"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-213, TASK-214]
ac-mapping: [AC-007, AC-008, AC-009]
imp-requirements: [REQ-002]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS API24 Stage app scaffold, signing baseline, GPLv3 bundle]
---

# TASK-301: API 24 Stage 工程与签名侧载基线

**功能描述**: 在 Windows/真实 115 门禁后，用 DevEco Studio 6.1.1 Release 生成 API 24 Stage 模型 entry HAP，配置精确工具链、最小权限、签名侧载和许可证。

**规格映射**: AC-007、AC-008、AC-009

## 外部依赖风险

- **依赖**: DevEco Studio/SDK、开发者签名与 API 24 真机。
- **状态**: 工具链版本固定，但签名和设备由开发环境提供。
- **缓解**: 使用 DevEco 生成 scaffold，不手写过时 Hvigor wrapper；签名不入 Git；只完成探针所需最小工程，功能开发等待 TASK-312。

## 验收条件

- [ ] 使用 HarmonyOS 6.1.1 Release API 24、ArkTS/ArkUI、Stage 模型和原生 AVPlayer 基线；对应 AC-007。
- [ ] 产物使用开发者签名侧载，不创建 AppGallery 公开发布流程；对应 AC-008。
- [ ] HAP/源码包含 GPLv3 和第三方/移植来源声明；对应 AC-009。

## Definition of Ready

- [ ] TASK-213 的 AC-130 Windows 门禁通过且 TASK-214 清理完成。
- [ ] AC-131 API 24 设备探针计划和真实设备可用；本任务完成后立即执行 TASK-312。
- [ ] DevEco Studio 6.1.1.280、SDK 6.1.1(24)、Hvigor 6.24.2、ohpm 6.1.2.268、Node 18.20.1 可用。

## 技术上下文

- `compileSdkVersion/targetSdkVersion=6.1.1(24)`；Stage/EntryAbility，不使用 FA 或 ArkUI-X。
- `module.json5` 只声明 INTERNET 和确实需要的系统能力；应用私有文件不请求媒体库权限。
- 新建 Navigation/NavPathStack 和 feature skeleton，后续任务按目录所有权填充。

## 实现文件（仅文件名）

**创建**:

- `harmony/AppScope/app.json5` - 应用标识/资源。
- `harmony/build-profile.json5` - API 24/签名引用/strictCheckerOnly。
- `harmony/hvigor/wrapper/hvigor-config.json5` - Hvigor 6.24.2。
- `harmony/entry/src/main/module.json5` - Stage EntryAbility/INTERNET。
- `harmony/entry/src/main/ets/entryability/EntryAbility.ets` - 生命周期和首屏。
- `harmony/entry/src/main/ets/pages/Index.ets` - Navigation 根骨架。
- `harmony/LICENSE`、`harmony/THIRD_PARTY_NOTICES.md` - GPLv3/来源。
- `harmony/entry/src/ohosTest/ets/test/Scaffold.test.ets` - 配置/Ability 启动测试。

## 测试说明

- Hvigor sync、ArkTS strict check、debug/release HAP 构建和开发者签名侧载。
- 检查 Stage model、API 24、唯一 EntryAbility、无 FA/Android/Flutter 依赖和无公开商店配置。
- 真机启动/前后台/退出，无 debug 签名用于最终 release。

## Definition of Done

- [ ] API 24 Stage 工程、精确工具链和侧载签名基线完成。
- [ ] 许可证随 HAP/工程保留。
- [ ] 最小探针 HAP 可供 TASK-312 验证，尚未开始鸿蒙业务功能开发。

**依赖**: TASK-213, TASK-214

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-301.md"`
