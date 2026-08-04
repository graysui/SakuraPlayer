---
id: TASK-301
title: "API 24 Stage 工程与签名侧载基线"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: implemented
dependencies: [TASK-213, TASK-214]
ac-mapping: [AC-007, AC-008, AC-009, AC-131]
imp-requirements: [REQ-002]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS API24 Stage app scaffold, SDK/build baseline, signing baseline, GPLv3 bundle]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-301: API 24 Stage 工程与签名侧载基线

**功能描述**: 在 Windows/真实 115 门禁后，用已安装版本的 DevEco Studio 生成 API 24 Stage 模型 entry HAP，配置精确工具链、最小权限、开发者签名侧载产物和许可证；不要求连接 API 24 物理真机。

**规格映射**: AC-007、AC-008、AC-009、AC-131

## 外部依赖风险

- **依赖**: DevEco Studio/SDK、开发者签名和 API 24 SDK 能力；不依赖物理真机。
- **状态**: 工具链版本已按开发机安装结果固定，签名材料由开发环境提供。
- **缓解**: 使用 DevEco 生成 scaffold，不手写过时 Hvigor wrapper；签名不入 Git；用 SDK 签名核验、构建和 fixture 检查替代设备探针。

## 验收条件

- [x] 使用 HarmonyOS 6.1.1 Release API 24、ArkTS/ArkUI、Stage 模型和原生 AVPlayer 基线；对应 AC-007。
- [x] 产物使用开发者签名并可供侧载，不创建 AppGallery 公开发布流程；对应 AC-008。
- [x] HAP/源码包含 GPLv3 和第三方/移植来源声明；对应 AC-009。

## Definition of Ready

- [x] TASK-213 的 AC-130 Windows 门禁通过且 TASK-214 清理完成。
- [x] AC-131 的 API 24 SDK 签名、构建和 fixture 验证范围已确定；本任务完成后进入 TASK-302 及后续功能任务。
- [x] DevEco Studio 6.1.1.290、SDK API 24（包标记 6.1.1.125）、Hvigor 6.24.3、ohpm 6.1.2.285、DevEco 内置 Node 18.20.1 可用。

## 技术上下文

- `compileSdkVersion/targetSdkVersion=6.1.1(24)`；Stage/EntryAbility，不使用 FA 或 ArkUI-X。
- `module.json5` 只声明 INTERNET 和确实需要的系统能力；应用私有文件不请求媒体库权限。
- 新建 Navigation/NavPathStack 和 feature skeleton，后续任务按目录所有权填充。

## 实现文件（仅文件名）

**创建**:

- `harmony/AppScope/app.json5` - 应用标识/资源。
- `harmony/build-profile.json5` - API 24/签名引用/strictCheckerOnly。
- `harmony/hvigor/wrapper/hvigor-config.json5` - Hvigor 6.24.3。
- `harmony/entry/src/main/module.json5` - Stage EntryAbility/INTERNET。
- `harmony/entry/src/main/ets/entryability/EntryAbility.ets` - 生命周期和首屏。
- `harmony/entry/src/main/ets/pages/Index.ets` - Navigation 根骨架。
- `harmony/LICENSE`、`harmony/THIRD_PARTY_NOTICES.md` - GPLv3/来源。
- `harmony/entry/src/ohosTest/ets/test/Scaffold.test.ets` - 配置/Ability 启动测试。

## 测试说明

- Hvigor sync、ArkTS strict check、debug/release HAP 构建、HAP 内容检查和开发者签名配置检查。
- 检查 Stage model、API 24、唯一 EntryAbility、无 FA/Android/Flutter 依赖和无公开商店配置；不连接物理真机。
- 使用 ohosTest/fixture 验证工程配置、生命周期和 API 24 签名引用；无 debug 签名用于最终 release。

## Definition of Done

- [x] API 24 Stage 工程、精确工具链和可侧载签名基线完成。
- [x] 许可证随 HAP/工程保留。
- [ ] 最小 Stage HAP 和 API 24 SDK/fixture 基线可供后续鸿蒙任务使用，尚未开始鸿蒙业务功能开发（ohosTest 待模拟器运行确认）。

**依赖**: TASK-213, TASK-214

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-301.md"`
