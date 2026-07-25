---
id: TASK-204
title: "媒体库网格、筛选与进度卡片"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-203]
ac-mapping: [AC-063, AC-064, AC-067, AC-068, AC-077]
imp-requirements: [REQ-013, REQ-015]
cross-boundary: false
external-dependency-risk: false
provides: [movie library grid, filters, progress card]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-204: 媒体库网格、筛选与进度卡片

**功能描述**: 实现去重影片网格、六分类和叠加标签/来源/可播放/大小/收藏筛选、默认发布日期排序及卡片播放进度。

**规格映射**: AC-063、AC-064、AC-067、AC-068、AC-077

## 验收条件

- [ ] 媒体库一个去重影片网格，六分类为可组合筛选；对应 AC-063。
- [ ] 默认 AVdb 发布日期降序，支持字幕/破解/4K/有码、来源、可播放和资源大小；对应 AC-064。
- [ ] 页面只渲染 core_ready 正式卡片；对应 AC-067。
- [ ] 播放按钮显示影片级进度或已看完；对应 AC-068。
- [ ] 收藏筛选使用 `favorite=true` 分页浏览单一影片收藏集合；对应 AC-077。

## Definition of Ready

- [ ] TASK-203 Shell/route 和 Movies API DTO 可用。
- [ ] 卡片尺寸、海报宽高比、分页和最大筛选栏宽度已按桌面设计系统确定。
- [ ] 筛选状态只保存本机页面，不跨设备同步。

## 技术上下文

- 网格使用稳定 track/min width，加载/角标/进度不能引发布局位移。
- 标签用独立筛选 chip/checkbox，不把属性做成互斥分段。
- 失败追加保留已加载项并提供局部重试。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/library/data/movies_api.dart` - 游标和筛选 DTO。
- `windows/lib/features/library/presentation/library_controller.dart` - 分页/筛选/恢复。
- `windows/lib/features/library/presentation/library_page.dart` - 桌面网格。
- `windows/lib/features/library/presentation/movie_card.dart` - 固定卡片/进度按钮。
- `windows/lib/features/library/presentation/library_filters.dart` - 组合筛选。
- `windows/test/features/library/library_controller_test.dart` - 参数/分页。
- `windows/test/features/library/library_page_test.dart` - 卡片/筛选/进度。

## 测试说明

**单元/Widget**:

- 六分类多选、四标签叠加、来源/可播放/大小/收藏、默认排序请求参数。
- core_ready-only fixture、重复来源仍一个影片卡、进度/完成按钮状态。
- 空/加载/追加失败/窄窗口/长标题不溢出。

## Definition of Done

- [ ] 网格、筛选、分页和进度卡片完成。
- [ ] 属性筛选非互斥且默认排序正确。
- [ ] Widget/controller 测试通过。

**依赖**: TASK-203

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-204.md"`
