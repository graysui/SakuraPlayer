---
id: TASK-307
title: "HarmonyOS 影片详情多来源与收藏"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
completed-at: 2026-08-06
dependencies: [TASK-304, TASK-306]
ac-mapping: [AC-031, AC-033, AC-034, AC-035, AC-068, AC-074, AC-077, AC-078]
imp-requirements: [REQ-007, REQ-013, REQ-015]
cross-boundary: false
external-dependency-risk: false
provides: [HarmonyOS movie detail and source selector]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-307: HarmonyOS 影片详情多来源与收藏

**功能描述**: 构建移动详情页、写真/演员/标签、影片进度、单一收藏和多来源选择 sheet。

**规格映射**: AC-031、AC-033 至 AC-035、AC-068、AC-074、AC-077、AC-078

## 验收条件

- [x] 展示规格全部影片字段和影片级进度；对应 AC-068、AC-074。
- [x] 多来源独立显示并可选择，字幕/破解/4K/有码可同时出现；对应 AC-031、AC-033、AC-034。
- [x] 资源大小/真实视频文件大小按状态使用正确名称；对应 AC-035。
- [x] 单一收藏，无历史/自定义播放列表入口；对应 AC-077、AC-078。

## Definition of Ready

- [x] TASK-304 MovieCard、TASK-306 Actor route、MovieDetail API 可用。
- [x] source_id 是后续唯一播放输入。
- [x] 使用 UIContext.openBindSheet，不使用 deprecated CustomDialog。

## 技术上下文

- 详情使用 List/Scroll 平铺区块，来源选择用 bottom sheet。
- 大图按需，长标题/标签/别名必须换行且不遮按钮。
- 不显示磁力、上游 URL 或外部播放器。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/movies/MovieDetailStore.ets` - 加载/收藏/来源。
- `harmony/entry/src/main/ets/features/movies/MovieDetailPage.ets` - 移动详情。
- `harmony/entry/src/main/ets/features/movies/SourceSheet.ets` - 多来源/标签/大小。
- `harmony/entry/src/ohosTest/ets/test/MovieDetail.test.ets` - 全字段/收藏/进度。
- `harmony/entry/src/ohosTest/ets/test/SourceSheet.test.ets` - 标签/状态/选择。

## 测试说明

- 完整/部分富化、多演员/图片/标签、多来源、长文本和大字体。
- 叠加标签规则、raw vs ready 大小、选择只产生 source_id。
- 无历史/播放列表/外部播放器 action。

## Definition of Done

- [x] 详情、多来源、收藏和导航完成。
- [x] source sheet 使用非 deprecated API（UIContext.openBindSheet）。
- [x] Hypium/UiTest 通过。

**实现证据**: `MovieDetailStore.ets`（generation 竞态/收藏在途防重/受限详情不收藏/跨影片清空来源选择）、
`MovieDetailPage.ets`（连续滚动单面：资料头/受限状态/来源/简介/剧照；播放按钮未选来源禁用；
进度文案播放/继续播放 N%/已看完）、`SourceSheet.ets`（openBindSheet 选择只产出 source_id；
rejected 永久禁用；六状态与大小文案按 Windows 契约）、`CatalogImage.ets` +
`core/images/CatalogImageCache.ets`（认证图片白名单校验/严格 UUID/内存 LRU/退出登录清理）、
`ApiModels.ets`（MovieDetail/MovieSource 严格 DTO）；ohosTest 模拟器实测 **129/129 全绿**，
debug/release HAP 构建成功且 `verify-app success`（API 24、INTERNET 最小权限、唯一 EntryAbility）。

**依赖**: TASK-304, TASK-306

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-307.md"`
