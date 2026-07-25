---
id: TASK-304
title: "HarmonyOS 媒体库网格筛选与进度"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-303]
ac-mapping: [AC-063, AC-064, AC-067, AC-068, AC-077]
imp-requirements: [REQ-013, REQ-015]
cross-boundary: false
external-dependency-risk: false
provides: [HarmonyOS media library grid and filters]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-304: HarmonyOS 媒体库网格筛选与进度

**功能描述**: 使用 LazyForEach/Grid/响应式 breakpoint 实现去重影片网格、六分类/标签/来源/可播放/大小/收藏筛选和进度按钮。

**规格映射**: AC-063、AC-064、AC-067、AC-068、AC-077

## 验收条件

- [ ] 一个去重影片网格，六分类可组合；对应 AC-063。
- [ ] 默认发布日期降序，支持四标签、来源、可播放和资源大小；对应 AC-064。
- [ ] 只显示 core_ready 正式卡片；对应 AC-067。
- [ ] 播放按钮显示影片级进度/已看完；对应 AC-068。
- [ ] 收藏筛选使用 `favorite=true` 分页浏览单一影片收藏集合；对应 AC-077。

## Definition of Ready

- [ ] TASK-303 根导航和 typed Movies API 可用。
- [ ] phone portrait/landscape breakpoint 和 Grid 列数已定义。
- [ ] 列表 item key 使用 movie ID，不能使用 index。

## 技术上下文

- 长列表使用 LazyForEach/@ReusableV2 或已验证 API 24 等价模式。
- if/else 切换布局，不用 Visibility.None 保留隐藏大网格。
- `build()` 无副作用，分页/加载在 Store/lifecycle 中。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/library/LibraryStore.ets` - 游标/筛选。
- `harmony/entry/src/main/ets/features/library/LibraryPage.ets` - Grid/List 响应式页面。
- `harmony/entry/src/main/ets/features/library/MovieCard.ets` - 可复用卡片/进度。
- `harmony/entry/src/main/ets/features/library/LibraryFilters.ets` - 组合筛选 sheet。
- `harmony/entry/src/ohosTest/ets/test/LibraryStore.test.ets` - 参数/分页。
- `harmony/entry/src/ohosTest/ets/test/LibraryPage.test.ets` - UiTest 网格/筛选。

## 测试说明

- 六分类多选、标签叠加、来源/可播放/大小/收藏、默认排序。
- core_ready-only、重复来源一个卡、进度/完成按钮、空/加载/追加错误。
- 直屏/横屏/字体放大/长标题不重叠，列表滚动按 movie ID 稳定复用。

## Definition of Done

- [ ] 媒体库、筛选、分页和进度完成。
- [ ] 大列表使用懒加载且无 build 副作用。
- [ ] Hypium/UiTest 通过。

**依赖**: TASK-303

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-304.md"`
