# Change Specification: TASK-204 Windows 媒体库客户端边界

**Type**: Delta
**Date**: 2026-07-30
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-204 的 Definition of Ready 把 Movies API DTO 写成 TASK-203 的既有产物，但 TASK-203 的正式范围和实际提交只交付 Shell、搜索与缓存角标，TASK-204 文件清单又明确由自身创建 `movies_api.dart`。同时任务要求桌面网格参数已确定，却没有冻结数值。本变更修正所有权并补齐可执行的桌面布局、认证图片、分页并发与失败恢复边界，不改变后端 `/movies` 行为或新增产品能力。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### Windows 媒体库确定性客户端协议

**Requirements**:

- REQ-CHG-119: TASK-204 拥有 Windows `MovieSummary`、`PlaybackProgress`、`MoviePage`、筛选与游标 DTO/API。它直接消费已冻结的 `GET /api/v1/movies`；TASK-203 只提供 `/app/library` Shell route，不拥有 Movies API DTO。搜索可复用 TASK-204 的公共影片摘要 DTO，但不得反向改变 `/search` 契约。
- REQ-CHG-120: 客户端固定请求 `limit=24`，初始排序为 `publish_date_desc`。`categories` 与 `labels` 以 OpenAPI 的逗号分隔形式发送；空选择不发送参数。客户端不得自行过滤 `core_ready`、按来源展开卡片或二次组合来源条件。
- REQ-CHG-121: Windows 网格海报宽高比固定为 `2:3`，最小网格 track 为 `184px`，横纵间距为 `16px`，卡片主轴高度固定为 `408px`。卡片封面、角标、加载和进度状态不得改变卡片或网格几何；缺图、认证图片失败和长标题使用固定占位与省略。
- REQ-CHG-122: 页面水平内边距在可用内容宽度小于 `900px` 时为 `16px`，否则为 `24px`；筛选内容最大宽度为 `1180px` 并左对齐。筛选按多选分类、多选标签、单选来源、三态可播放、最小/最大 MiB、收藏与排序表达，不把独立属性做成互斥组合。
- REQ-CHG-123: 当距离滚动底部不大于 `480px` 且存在 `next_cursor` 时只允许一个追加请求。筛选变化递增请求 generation、清空旧游标并重新加载第一页；旧 generation 的成功或失败都不得回写。游标校验失败按当前筛选重新加载第一页，不复用旧游标。
- REQ-CHG-124: 初始失败显示整页重试；追加失败必须保留既有卡片与 `next_cursor` 并只显示局部重试。重复触底不得重复追加。空结果、初始加载、初始失败、追加加载和追加失败是互斥且可测试的页面状态。
- REQ-CHG-125: `cover_url` 只接受 `/api/v1/catalog/images/{uuid}` 形式并通过现有认证 `ApiClient` 读取字节；不得匿名加载、接受绝对 URL或绕过安全相对路径校验。`duration_seconds=null` 时显示已播放时长但不计算百分比；`completed=true` 显示已看完，否则已知正时长将百分比夹在 0% 至 100%。

**Acceptance Criteria**:

- [x] API 测试覆盖完整默认参数、每类筛选、空参数省略、严格 DTO 和认证封面路径。
- [x] Controller 测试覆盖筛选快速切换、迟到响应、游标失效、重复触底、追加失败保留与局部重试。
- [x] Widget 测试覆盖网格去重输入、固定几何、缺图/图片失败、长标题、进度/完成、空/加载/失败和窄窗口。

**Impact**: AC-063、AC-064、AC-067、AC-068、AC-077、TASK-204、Windows 媒体库客户端契约、功能规格和追踪矩阵；Breaking: NO，后端接口不变且 Windows 媒体库尚未实现。

## MODIFIED

### TASK-204 Definition of Ready 与文件所有权

**Previous Behavior**: TASK-204 要求 TASK-203 已提供 Movies API DTO，同时又声明自己创建 `movies_api.dart`；桌面布局参数没有数值。

**New Behavior**: TASK-203 只需提供 Shell/route；TASK-204 自身拥有 Movies API DTO/API。桌面尺寸、分页、认证图片、并发和失败恢复由 [Windows 媒体库客户端契约](../contracts/windows-library-client.md) 冻结。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-204 DoR | MODIFIED | LOW |
| Windows library DTO/controller/UI | ADDED | MEDIUM |
| `/movies` OpenAPI/backend | UNCHANGED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-204 的依赖或 AC 映射。变更规格、客户端契约、功能规格、TASK-204 和追踪矩阵先独立提交；TASK-204 实现、测试、状态与交接仍在后续 TASK-204 中文提交中完成。

## Testing Strategy

- Dart 单元测试固定筛选查询编码、DTO 校验、generation 与游标状态机。
- Flutter Widget 测试固定网格几何、响应式筛选、卡片视觉状态和分页失败恢复。
- Fast 运行 `dart format`、`flutter analyze` 和完整 `flutter test`；Final 运行 Windows debug build，不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-204 实现提交前可整体回退本变更。实现提交后只能通过新的前向变更调整客户端布局或状态语义，不得让客户端偏离已冻结的 `/movies` 过滤、游标、认证图片和 DTO 契约。
