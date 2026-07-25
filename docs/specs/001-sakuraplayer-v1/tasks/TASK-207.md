---
id: TASK-207
title: "影片详情多来源与收藏"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-204, TASK-206]
ac-mapping: [AC-031, AC-033, AC-034, AC-035, AC-068, AC-074, AC-077, AC-078]
imp-requirements: [REQ-007, REQ-013, REQ-015]
cross-boundary: false
external-dependency-risk: false
provides: [Windows movie detail and source selector]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-207: 影片详情多来源与收藏

**功能描述**: 实现聚合影片详情、演员/标签/图片、影片进度、单一收藏和像 Emby 一样的多来源选择列表。

**规格映射**: AC-031、AC-033 至 AC-035、AC-068、AC-074、AC-077、AC-078

## 验收条件

- [ ] 详情显示规格要求的封面、中日标题、番号、日期、厂商、系列、导演、演员、标签、评分、简介、剧照、进度和收藏；对应 AC-074。
- [ ] 多个 AVdb 来源独立列出并支持选择，字幕/破解/4K/有码标签可叠加；对应 AC-031、AC-033、AC-034。
- [ ] 离线前显示“资源大小”，ready 后显示“视频文件大小”；对应 AC-035。
- [ ] 播放按钮显示影片级进度/已看完；收藏单一且无历史页；对应 AC-068、AC-077、AC-078。

## Definition of Ready

- [ ] TASK-204 MovieCard、TASK-206 Actor navigation 和 MovieDetail API 可用。
- [ ] 来源标签、availability、两个大小字段 DTO 明确。
- [ ] 播放操作只传 source_id 给 TASK-209。

## 技术上下文

- 详情首屏不嵌套装饰卡片；资源是可扫描列表/表格，不是互斥分类 Tab。
- 长标题、番号、标签和来源标题需要约束换行/省略，不覆盖操作区。
- 不显示磁力、帖子 secret 或外部播放器操作。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/movies/data/movie_detail_api.dart` - 聚合详情 DTO/API。
- `windows/lib/features/movies/presentation/movie_detail_controller.dart` - 加载/收藏/来源选择。
- `windows/lib/features/movies/presentation/movie_detail_page.dart` - 桌面详情布局。
- `windows/lib/features/movies/presentation/source_list.dart` - 来源标签/大小/状态。
- `windows/test/features/movies/movie_detail_test.dart` - 聚合字段/收藏/进度。
- `windows/test/features/movies/source_list_test.dart` - 多来源/标签/大小。

## 测试说明

- 全字段、部分富化缺失、占位图片、多个演员/标签/来源。
- 字幕+破解+4K+有码同时显示；亚洲无码无证据不显示破解。
- raw/queued/running/ready/failed/rejected 状态和大小标签；无历史/播放列表入口。

## Definition of Done

- [ ] 详情、来源、收藏和进度显示完成。
- [ ] 来源选择只输出 source_id。
- [ ] 多来源和响应式布局测试通过。

**依赖**: TASK-204, TASK-206

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-207.md"`
