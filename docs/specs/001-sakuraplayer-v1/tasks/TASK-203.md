---
id: TASK-203
title: "桌面 Shell、全局搜索与缓存角标"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-202]
ac-mapping: [AC-059, AC-060, AC-061, AC-065, AC-066, AC-118]
imp-requirements: [REQ-012, REQ-013, REQ-021]
cross-boundary: false
external-dependency-risk: false
provides: [desktop shell, global search, cache badge]
---

# TASK-203: 桌面 Shell、全局搜索与缓存角标

**功能描述**: 实现 Windows 左侧三入口 Shell、顶部全局搜索/缓存/设置工具和影片/女优分组搜索补全状态。

**规格映射**: AC-059 至 AC-061、AC-065、AC-066、AC-118

## 验收条件

- [ ] 左侧导航只包含媒体库、排行榜、女优；对应 AC-059、AC-060。
- [ ] 顶部提供全局搜索、缓存状态和设置入口；对应 AC-061。
- [ ] 搜索番号/标题/演员姓名/别名并按影片/女优分组；raw-only 显示正在补全并自动刷新；对应 AC-065、AC-066。
- [ ] 缓存入口显示 queued/running/ready 数量角标；对应 AC-118。

## Definition of Ready

- [ ] TASK-202 API/event/snapshot 可提供 search 和 capacity DTO。
- [ ] Shell 与 fullscreen player 路由边界已确认。
- [ ] 搜索输入 debounce 只影响 UI，不改变后端优先级语义。

## 技术上下文

- 桌面页面使用稳定宽度侧栏和顶部工具，不用移动 bottom nav。
- 搜索补全监听 catalog.movie.core_ready 事件，跳号时 snapshot/重新查询。
- 角标固定尺寸，数量变化不能推动工具栏布局。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/widgets/shell/desktop_shell.dart` - 侧栏/顶部栏/内容区。
- `windows/lib/features/search/data/search_api.dart` - search DTO/API。
- `windows/lib/features/search/presentation/search_controller.dart` - 分组/补全状态。
- `windows/lib/features/search/presentation/search_overlay.dart` - 搜索交互。
- `windows/lib/features/cache/presentation/cache_badge.dart` - 固定角标。
- `windows/test/widgets/desktop_shell_test.dart` - 导航/工具/角标。
- `windows/test/features/search/search_controller_test.dart` - 分组/自动刷新。

## 测试说明

**单元/Widget**:

- 三个导航项及 active route；顶部三个入口；窄窗口文本不溢出。
- 番号/标题/别名结果分组，pending 事件完成后替换正式影片。
- capacity 0/1/10 和重连 snapshot 更新角标但不改变布局。

## Definition of Done

- [ ] Shell、搜索、补全和角标完成。
- [ ] 不出现发现、历史、订阅或下载器导航。
- [ ] Widget/controller 测试通过。

**依赖**: TASK-202

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-203.md"`
