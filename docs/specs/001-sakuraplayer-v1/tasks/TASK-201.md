---
id: TASK-201
title: "Flutter Windows 脚手架、主题与认证壳"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
implemented_date: 2026-07-29
completed_date: 2026-07-29
dependencies: [TASK-114]
ac-mapping: [AC-005, AC-009, AC-062, AC-104]
imp-requirements: [REQ-002, REQ-012, REQ-019]
cross-boundary: false
external-dependency-risk: false
provides: [Flutter Windows app scaffold, theme, typed routes, login shell]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-201: Flutter Windows 脚手架、主题与认证壳

**功能描述**: 新建仅 Windows 的 Flutter 3.29.2 工程，固定依赖、Riverpod/手写 typed routes、主题、登录壳和 GPLv3 声明。

**实施边界**: [TASK-201 Windows 脚手架实施边界](../changes/2026-07-29--task-201-scaffold-boundaries.md)

**规格映射**: AC-005、AC-009、AC-062、AC-104

## 验收条件

- [x] 工程只启用 Windows 10/11 目标并可完成 Windows debug build；对应 AC-005。release 与私有安装包归 TASK-212。
- [x] GPLv3 和第三方声明随工程保留，产物核验归 TASK-212；对应 AC-009。
- [x] 应用支持系统浅/深主题，播放器主题接口固定深色；对应 AC-062。
- [x] 桌面路由预留可替换 Shell 和应用内全屏播放器，不实现外部播放器；对应 AC-104。最终左侧导航归 TASK-203。

## Definition of Ready

- [x] TASK-114 已完成，后端认证/目录 OpenAPI 与 Phase 2 契约可用。
- [x] Flutter/Dart/media_kit/Riverpod/go_router 版本与架构一致；typed routes 不使用代码生成。
- [x] 不创建 Android/iOS/macOS/Linux/Web 目录。

## 技术上下文

- feature-first，Riverpod 是唯一业务状态方案。
- composition root 预建 feature 空入口，后续任务只修改自有目录。
- `AuthSessionState` 只提供可注入的未认证/已认证状态；真实 token/session 归 TASK-202。
- 登录后才能进入 Shell 占位页；最终 Shell 归 TASK-203；无年龄确认路由。

## 实现文件（仅文件名）

**创建**:

- `windows/pubspec.yaml` - 固定依赖和 Windows-only 设置。
- `windows/.metadata`、`windows/analysis_options.yaml`、`windows/pubspec.lock` - Flutter 工程元数据、分析规则和依赖锁。
- `windows/windows/` - Flutter 生成的 Windows runner、CMake 和插件注册文件。
- `windows/lib/main.dart` - bootstrap/MediaKit 初始化。
- `windows/lib/app/app.dart` - MaterialApp.router/ProviderScope。
- `windows/lib/routes/app_router.dart` - typed auth/Shell/fullscreen 路由骨架。
- `windows/lib/features/auth/domain/auth_session_state.dart` - TASK-202 可替换的最小会话状态接口。
- `windows/lib/theme/` - 明暗 token 和播放器深色主题。
- `windows/lib/features/auth/presentation/login_page.dart` - 登录壳。
- `windows/test/app/app_bootstrap_test.dart` - 平台/主题/路由测试。
- `windows/LICENSE`、`windows/THIRD_PARTY_NOTICES.md` - GPLv3 与来源。

## 测试说明

**单元/Widget**:

- 无会话只能见登录；注入已认证状态后进入 Shell 占位；不存在年龄确认/外部播放器路由。
- light/dark/system 切换和播放器深色不受应用主题影响。

**构建检查**:

- `flutter analyze`、`flutter test` 和 Windows debug build；确认仓库没有非 Windows 平台工程。

## Definition of Done

- [x] Windows-only debug 脚手架、主题、路由和许可证完成。
- [x] 固定依赖可解析且基础构建通过。
- [x] 不含非目标平台或外部播放器入口。

## Implementation Summary

- 使用 Flutter 3.29.2/Dart 3.7.2 生成仅 Windows 工程，锁定 flutter_riverpod 3.1.0、
  go_router 16.3.0、media_kit 1.1.11、media_kit_video 1.2.5 和
  media_kit_libs_video 1.0.5；未引入路由代码生成或其他平台 runner。
- 建立 ProviderScope/MaterialApp.router 组合根、可注入 `AuthSessionState`、登录/Shell/全屏
  播放器手写强类型路由、浅/深/系统主题和固定深色播放器主题；真实认证与最终 Shell 保持由
  TASK-202/TASK-203 接管。
- GPL-3.0-only 文本、Flutter/Riverpod/go_router/media_kit 精确版本与 libmpv 构建来源已写入
  Windows 工程，release 产物审计继续归 TASK-212。
- `dart format`、`flutter analyze`、7 项 `flutter test`、Windows debug build 和可执行文件
  3 秒启动冒烟通过；工程目录测试确认不存在 Android/iOS/Linux/macOS/Web runner。

**完成日期**: 2026-07-29

**依赖**: TASK-114

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-201.md"`
