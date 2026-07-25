---
id: TASK-201
title: "Flutter Windows 脚手架、主题与认证壳"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-014]
ac-mapping: [AC-005, AC-008, AC-009, AC-059, AC-062, AC-104]
imp-requirements: [REQ-002, REQ-012, REQ-019]
cross-boundary: false
external-dependency-risk: false
provides: [Flutter Windows app scaffold, theme, typed routes, login shell]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-201: Flutter Windows 脚手架、主题与认证壳

**功能描述**: 新建仅 Windows 的 Flutter 3.29.2 工程，固定依赖、Riverpod/typed routes、主题、登录壳、私有发布和 GPLv3 声明。

**规格映射**: AC-005、AC-008、AC-009、AC-059、AC-062、AC-104

## 验收条件

- [ ] 工程只启用 Windows 10/11 目标并可生成私有安装产物；对应 AC-005、AC-008。
- [ ] GPLv3、第三方声明和移植来源随工程/产物保留；对应 AC-009。
- [ ] 应用支持系统浅/深主题，播放器主题接口固定深色；对应 AC-062。
- [ ] 桌面路由预留左侧导航和应用内播放器，不实现外部播放器；对应 AC-059、AC-104。

## Definition of Ready

- [ ] TASK-014 后端认证/目录 OpenAPI 可用。
- [ ] Flutter/Dart/media_kit/Riverpod/go_router 版本与架构一致。
- [ ] 不创建 Android/iOS/macOS/Linux/Web 目录。

## 技术上下文

- feature-first，Riverpod 是唯一业务状态方案。
- composition root 预建 feature 空入口，后续任务只修改自有目录。
- 登录后才能进入 Shell；无年龄确认路由。

## 实现文件（仅文件名）

**创建**:

- `windows/pubspec.yaml` - 固定依赖和 Windows-only 设置。
- `windows/lib/main.dart` - bootstrap/MediaKit 初始化。
- `windows/lib/app/app.dart` - MaterialApp.router/ProviderScope。
- `windows/lib/routes/app_router.dart` - typed auth/Shell/fullscreen 路由骨架。
- `windows/lib/theme/` - 明暗 token 和播放器深色主题。
- `windows/lib/features/auth/presentation/login_page.dart` - 登录壳。
- `windows/test/app/app_bootstrap_test.dart` - 平台/主题/路由测试。
- `windows/LICENSE`、`windows/THIRD_PARTY_NOTICES.md` - GPLv3 与来源。

## 测试说明

**单元/Widget**:

- 无会话只能见登录；有会话进入桌面 Shell；不存在年龄确认/外部播放器路由。
- light/dark/system 切换和播放器深色不受应用主题影响。

**构建检查**:

- `flutter analyze`、`flutter test` 和 Windows debug build；确认仓库没有非 Windows 平台工程。

## Definition of Done

- [ ] Windows-only 脚手架、主题、路由和许可证完成。
- [ ] 固定依赖可解析且基础构建通过。
- [ ] 不含非目标平台或外部播放器入口。

**依赖**: TASK-014

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-201.md"`
