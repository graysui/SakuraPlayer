---
id: TASK-303
title: "Navigation 底部 Tab 主题搜索与角标"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-302]
ac-mapping: [AC-059, AC-060, AC-061, AC-062, AC-065, AC-066, AC-118]
imp-requirements: [REQ-012, REQ-013, REQ-021]
cross-boundary: false
external-dependency-risk: false
provides: [HarmonyOS Navigation root, bottom tabs, theme, search, cache badge]
---

# TASK-303: Navigation 底部 Tab 主题搜索与角标

**功能描述**: 使用 Navigation/NavPathStack 和 ArkUI V2 构建媒体库/排行榜/女优底部导航、顶部搜索/缓存/设置、系统明暗主题和缓存角标。

**规格映射**: AC-059 至 AC-062、AC-065、AC-066、AC-118

## 验收条件

- [ ] 手机端底部导航只有媒体库、排行榜、女优；对应 AC-059、AC-060。
- [ ] 顶部提供全局搜索、缓存状态和设置；对应 AC-061。
- [ ] 浅/深主题默认跟随系统，播放器页面独立深色；对应 AC-062。
- [ ] 搜索按影片/女优分组并处理“正在补全资料”；对应 AC-065、AC-066。
- [ ] 缓存入口显示 queued/running/ready 角标；对应 AC-118。

## Definition of Ready

- [ ] TASK-302 typed API/snapshot store 可用。
- [ ] 使用 Navigation/NavPathStack，不使用旧 router。
- [ ] API 24 V2 decorator/StateStore 签名从安装 SDK 验证。

## 技术上下文

- `Tabs(barPosition: End)` 仅承载三个根目的地；详情用 NavPathStack push。
- 主题颜色放 `resources/base` 与 `resources/dark` 同名资源。
- 使用 sys.symbol 前先验证名称存在，不猜图标名。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/app/AppNavigation.ets` - Navigation/NavPathStack。
- `harmony/entry/src/main/ets/app/BottomTabs.ets` - 三根 Tab。
- `harmony/entry/src/main/ets/features/search/SearchStore.ets` - 分组/补全。
- `harmony/entry/src/main/ets/features/search/SearchOverlay.ets` - 搜索 UI。
- `harmony/entry/src/main/ets/features/cache/CacheBadge.ets` - 固定角标。
- `harmony/entry/src/main/resources/base/element/color.json` - 浅色 token。
- `harmony/entry/src/main/resources/dark/element/color.json` - 深色 token。
- `harmony/entry/src/ohosTest/ets/test/AppNavigation.test.ets` - 导航/主题/搜索。

## 测试说明

- 三 Tab 导航栈保持、详情 push/pop、顶部三入口和角标 0/1/10。
- 系统明暗切换，播放器 route 始终深色。
- 番号/标题/别名分组，pending core_ready 事件自动刷新；长文本/字体缩放不重叠。

## Definition of Done

- [ ] Navigation、Tab、主题、搜索和角标完成。
- [ ] 无旧 router、发现/历史/订阅 Tab。
- [ ] Hypium/UiTest 基础测试通过。

**依赖**: TASK-302

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-303.md"`
