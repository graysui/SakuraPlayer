# Windows 影片详情客户端契约

**Status**: Accepted
**Date**: 2026-07-30
**Owner**: TASK-207

本契约固定 Windows 影片详情对既有 `/api/v1/movies/{movie_id}`、影片收藏和认证目录图片的消费、路由、来源选择、失败恢复与桌面布局。后端聚合顺序、来源可用性、影片进度和收藏真相继续以 `rest-api.openapi.yaml`、Catalog/Discovery 端口和 TASK-011/TASK-103/TASK-105/TASK-111 变更规格为准。

## 1. API 所有权与 DTO

- TASK-207 在 `windows/lib/features/movies/data/movie_detail_api.dart` 实现 `MovieDetailDto`、`MovieSourceDto` 与 MovieDetail gateway。影片摘要与进度复用 TASK-204 的 `MovieSummaryDto`/`PlaybackProgressDto`，演员复用 TASK-206 的 `ActorSummaryDto`；不得复制或放宽共享 DTO。
- `MovieDetailDto` 严格读取摘要字段、可空 `release_date/maker/series/director/score/description/description_original`、最多 100 个演员/标签/剧照/来源。标签、剧照 URL和来源 ID不得重复；客户端保持服务端集合顺序，不按显示文本重新匹配或排序。
- 封面和剧照只接受 `/api/v1/catalog/images/{uuid}`，并通过现有认证 `ApiClient` 读取字节。绝对 URL、路径穿越、非图片 API 路径和 GFriends URL 均不得进入目录图片 loader。
- `MovieSourceDto` 严格读取 UUID `id`、`sehuatang/x1080x`、整数帖子 ID、非空标题、可空日期、六分类之一、最多四个不重复来源标签、非负可空 `resource_size_mb/video_file_size_bytes`，以及 `available/queued/running/ready/failed/rejected`。客户端不得接受 `raw` 或未知状态。
- 收藏只调用 `PUT` 或 `DELETE movies/{movie_id}/favorite`，成功必须是空 `204`；请求不得携带标题、番号、来源、进度或图片字段。

## 2. 加载与收藏状态

- 详情按 MovieId 加载。切换 MovieId、认证服务端或会话必须增加 generation，清空旧详情、来源选择和收藏在途状态；旧 generation 的成功或失败均忽略。
- 初始加载显示稳定占位；普通失败显示重试；`resource_not_found` 显示“影片资料不存在”并允许返回，不把旧影片内容保留在新路由下。重试只请求当前 MovieId。
- 同一影片的收藏请求在途时禁用重复提交。成功后更新当前详情；失败保留服务端确认前的旧值并显示非阻断重试。不得通过连续点击并发翻转，也不得在失败时乐观保留未确认状态。
- TASK-207 不建立独立观看历史或自定义列表。影片收藏列表仍由 TASK-204 的 `favorite=true` 媒体库筛选读取；离开详情后的列表以自身下次刷新为准。

## 3. 路由与入口

- TASK-207 建立 `/app/movies/:movie_id` typed route；MovieId 必须先通过 UUID 路径段校验。非法路径重定向媒体库，详情在 Shell 中归属媒体库 destination。
- 媒体库 MovieCard、排行榜 MovieCard、女优详情关联 MovieCard 和全局搜索影片结果进入同一详情 route。搜索结果先关闭对话框；卡片正文与卡片播放按钮都只进入详情，不直接创建离线任务。
- 详情演员项只使用 TASK-206 的 `ActorDetailRoute(actor_id)`；不得按姓名、别名或 URL 建立演员路由。
- 详情返回优先弹出当前 route；没有可弹出的 route 时返回媒体库。导航不得丢失 MovieId 或把标题放入路径。

## 4. 来源选择与后续播放边界

- 页面初始不选择来源。用户必须明确选择一个非 rejected 来源，再点击详情播放按钮；选择行本身不得访问网络、创建缓存任务或自动播放。
- `available/queued/running/ready/failed` 均可选择：TASK-209 后续分别创建新任务、复用活动任务、复用 ready 任务或在失败后创建新请求。`rejected` 永久禁用且不得输出 SourceId。
- 点击可用的详情播放按钮只向注入的 TASK-209 边界输出当前 `source_id`。TASK-207 不生成 Idempotency-Key、不调用 play-request、不导航等待页或播放器，也不传磁力、帖子 ID、标题或 availability。
- 切换来源只更新本地选中状态；收藏、图片加载和页面重建不得清除当前仍存在的选择。切换 MovieId、详情重新加载后来源消失或认证变化必须清空选择。

## 5. 来源显示

- 来源保持服务端顺序，使用可扫描列表而不是分类 Tab。每行固定显示来源站点、分类、发布日期、标题、状态、大小和叠加标签；标题最多两行并省略，操作区尺寸稳定。
- 标签固定显示顺序为 `subtitle/cracked/4k/censored`，中文为“字幕/破解/4K/有码”。客户端只显示服务端标签，不根据“亚洲无码”、标题或分类自行推导破解/有码。
- 状态文案固定为：`available=可缓存`、`queued=排队中`、`running=处理中`、`ready=可播放`、`failed=上次失败`、`rejected=不可用`。
- `ready` 显示“视频文件大小”；值为空时显示“视频文件大小未知”，不得回退 AVdb 大小。其余状态显示“资源大小”；值为空时显示“资源大小未知”。MiB 按整数显示，视频字节使用二进制单位并最多保留一位小数。
- `source_count` 是服务端总数，可能大于当前最多 100 个嵌套来源；客户端显示总数，不虚构嵌套分页。

## 6. 详情布局

- 页面水平内边距在可用宽度小于 `900px` 时为 `16px`，否则为 `24px`；内容最大宽度 `1280px` 并左对齐。详情使用一个连续滚动面，不把页面区段包成浮动装饰卡。
- 宽布局资料头使用封面与资料双列，封面固定 `240x360px`；窄布局改为纵向并使用 `200x300px` 封面。长中日文标题与番号换行/省略，不覆盖返回、收藏或播放操作。
- `release_date` 优先作为影片日期，缺失时回退摘要 `publish_date`；中日标题、简介原文只有在与主要文本不同时才单独显示。缺失厂商、系列、导演、评分、简介、演员、标签或剧照分别使用稳定空状态，不阻断来源列表。
- 演员使用可换行的导航项；标签自然换行。剧照使用最小 track `220px`、`16:9`、间距 `12px` 的实际图片网格，单图失败只显示该图占位和重试。
- 来源列表行最小高度 `88px`。详情主播放按钮固定高度 `44px`，显示与 TASK-204 相同的“播放/继续播放/已看完”进度语义；未选择来源或未注入 TASK-209 sink 时禁用但保持几何稳定。

## 7. 验证

- API/DTO：完整/缺失富化、共享摘要/演员、集合上限与重复、日期、标签、availability、两个大小、认证图片路径、204 收藏与未知协议值。
- Controller：MovieId/generation、迟到响应、404/普通失败、重试、收藏在途/成功/失败、显式来源选择、rejected 禁用、选择失效和认证清理。
- Widget/Route：四类入口到详情、详情到演员、非法 UUID、返回、宽窄布局、长文本、缺图/字段/集合、剧照失败、叠加标签、六状态、大小文案、进度、收藏、无历史/列表入口和 source_id-only 输出。
