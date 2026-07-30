# Change Specification: TASK-207 Windows 影片详情客户端边界

**Type**: Delta
**Date**: 2026-07-30
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-207 的测试说明把来源初始状态写成 OpenAPI 不存在的 `raw`，实际公开值为 `available`。任务还没有冻结影片详情 route、四类入口、共享 DTO、认证剧照、加载/收藏恢复、来源各状态是否可选、真实大小缺失、显式选择与 TASK-209 的交接以及响应式布局。本变更修正冲突并补齐可执行的 Windows 影片详情客户端协议，不改变后端 `/movies/{movie_id}`、收藏、availability、进度或播放请求行为。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### Windows 影片详情确定性客户端协议

**Requirements**:

- REQ-CHG-165: TASK-207 拥有 Windows `MovieDetail`、`MovieSource` 与详情 gateway，直接消费已冻结的 `GET /api/v1/movies/{movie_id}` 和幂等收藏 PUT/DELETE。摘要/进度复用 TASK-204 DTO，演员复用 TASK-206 DTO，永久封面/剧照复用认证目录图片 loader，不复制或放宽共享协议。
- REQ-CHG-166: 详情和来源 DTO 的枚举、集合上限、重复、日期、非负大小与安全图片路径遵循 [Windows 影片详情客户端契约](../contracts/windows-movie-detail-client.md)。来源状态固定为 `available/queued/running/ready/failed/rejected`；删除任务中不存在的 `raw` 表述。
- REQ-CHG-167: TASK-207 建立 `/app/movies/:movie_id` UUID typed route，并把媒体库、排行榜、女优关联 MovieCard 和全局搜索影片结果接入同一详情。详情演员只进入 TASK-206 Actor route；非法 MovieId 返回媒体库。
- REQ-CHG-168: 切换 MovieId 或认证会话增加详情 generation 并清空旧状态，迟到成功/失败不得覆盖当前影片。普通失败可重试；`resource_not_found` 显示独立不存在状态。收藏在途禁用重复提交，成功更新当前详情，失败保留旧值并可重试。
- REQ-CHG-169: 页面初始不选择来源。用户明确选择一个非 rejected 来源并点击详情播放按钮后，只向 TASK-209 注入边界输出 SourceId；TASK-207 不创建离线任务、Idempotency-Key、等待页或播放器导航。`rejected` 禁止选择，其余五种状态允许交给后续任务新建或复用。
- REQ-CHG-170: 来源保持服务端顺序并显示站点、分类、日期、标题、状态、大小和可叠加标签。标签按 subtitle/cracked/4k/censored 固定顺序显示，不根据标题或分类重新推导；状态和大小文案由客户端契约冻结。
- REQ-CHG-171: `ready` 只显示真实 `video_file_size_bytes`，空值显示“视频文件大小未知”且不回退 AVdb 大小；其他状态显示 `resource_size_mb` 或“资源大小未知”。`source_count` 保持服务端总数，即使嵌套来源因 100 项上限被截断也不改写。
- REQ-CHG-172: 详情使用连续无嵌套装饰卡的滚动布局。页面 `<900px` 使用 `16px`、否则 `24px` 水平内边距，最大内容宽度 `1280px`；宽/窄封面分别固定 `240x360px` 和 `200x300px`。剧照最小 track `220px`、比例 `16:9`、间距 `12px`，来源行最小高度 `88px`。
- REQ-CHG-173: 影片日期优先 `release_date`、缺失时回退 `publish_date`；相同中日标题或简介不重复显示。部分富化、缺图、单张剧照失败和空集合必须保持其他详情与来源可用，长文本不得覆盖收藏、播放或来源操作区。
- REQ-CHG-174: 卡片正文和卡片播放按钮在 TASK-207 只进入详情，不直接请求播放。详情主播放按钮沿用 TASK-204 进度文案，未选择来源或尚未注入 TASK-209 sink 时保持固定尺寸并禁用；v1 不新增历史、自定义列表、磁力或外部播放器入口。

**Acceptance Criteria**:

- [ ] API/DTO 测试覆盖共享 DTO、全字段/缺失富化、集合与枚举、认证图片、六种 availability、两个大小和 204 收藏。
- [ ] Controller 测试覆盖 MovieId generation、迟到响应、失败/404、收藏成功/失败、显式来源选择、rejected 和认证清理。
- [ ] Widget/路由测试覆盖媒体库/排行榜/搜索/女优关联影片入口、Actor route、进度、长文本、剧照、来源列表、source_id-only 输出和宽窄布局。

**Impact**: AC-031、AC-033 至 AC-035、AC-068、AC-074、AC-077、AC-078、TASK-207、Windows 影片详情客户端契约、功能规格、任务索引和追踪矩阵；Breaking: NO，后端接口不变且 Windows 影片详情尚未实现。

## MODIFIED

### TASK-207 来源状态、路由与 TASK-209 交接

**Previous Behavior**: 测试说明要求不存在的 `raw`；route、入口、共享 DTO、收藏恢复、来源可选状态、大小空值和布局没有确定规则。

**New Behavior**: 使用公开 `available`，TASK-207 自身拥有影片详情 route、DTO/API、四类入口、详情状态与 source_id-only 选择输出。TASK-209 仍独占 play-request、等待页、通知和播放器衔接；确定性行为由 [Windows 影片详情客户端契约](../contracts/windows-movie-detail-client.md) 冻结。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-207 DoR/测试边界 | MODIFIED | LOW |
| Windows MovieDetail DTO/controller/routes/UI | ADDED | MEDIUM |
| MovieCard/搜索/Actor 关联影片入口 | MODIFIED | MEDIUM |
| `/movies/{movie_id}` OpenAPI/backend | UNCHANGED | LOW |
| TASK-209 play-request | UNCHANGED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-207 的依赖或 AC 映射。变更规格、客户端契约、功能规格、Windows 任务索引、TASK-207 和追踪矩阵先独立提交；TASK-207 实现、测试、状态与交接仍在后续 TASK-207 中文提交中完成。

## Testing Strategy

- Dart 单元测试固定详情/来源 DTO、认证图片、收藏、generation 和显式来源选择。
- Flutter Widget/路由测试固定四类入口、资料/剧照/来源、Actor 导航、进度、空/失败和响应式布局。
- Fast 运行 `dart format`、`flutter analyze` 和完整 `flutter test`；Final 运行 Windows debug build，不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-207 实现提交前可整体回退本变更。实现提交后只能通过新的前向变更调整客户端详情或来源语义，不得引入 `raw`、客户端重算标签、提前调用 play-request、暴露磁力或绕过认证图片读取。
