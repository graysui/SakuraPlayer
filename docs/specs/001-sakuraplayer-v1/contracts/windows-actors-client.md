# Windows 女优客户端契约

**Status**: Accepted
**Date**: 2026-07-30
**Owner**: TASK-206

本契约固定 Windows 女优页面对既有 `/api/v1/actors` 的消费、路由、收藏、GFriends 临时缓存和桌面布局。后端唯一身份匹配、可见性、集合顺序与 cursor 真相继续以 `rest-api.openapi.yaml` 和 TASK-009/TASK-011 变更规格为准。

## 1. API 所有权与 DTO

- TASK-206 在 `windows/lib/features/actors/data/actors_api.dart` 实现 `ActorSummaryDto`、`ActorDetailDto`、`ActorPageDto` 与 Actors gateway；TASK-204 提供严格 `MovieSummaryDto`、认证封面 loader 和 `MovieCard`。
- 列表固定发送 `limit=24`。查询去除首尾空白后必须为 1 至 200 个字符；空查询省略 `q`。普通模式省略 `favorite`，收藏模式只发送 `favorite=true`；cursor 原样回传。
- `ActorSummaryDto` 严格读取 UUID `id`、非空 `display_name`、可空 `name_ja/name_zh/profile_url`、最多 100 个不重复非空 `aliases` 和布尔 `favorite`。
- `ActorDetailDto` 复用 ActorSummary，并严格读取可空 `bio/bio_original`、最多 100 个不重复 `gallery_urls` 和最多 100 个 `MovieSummaryDto`。客户端保持服务端顺序，不按名称、URL 或影片字段重新匹配/排序。
- 收藏只调用 `PUT` 或 `DELETE actors/{actor_id}/favorite`，成功必须是空 `204`；客户端不得提交姓名、别名或图片 URL。

## 2. 列表状态与收藏

- 初始范围是普通模式、空查询。页面输入使用 `300ms` 防抖；按下 Enter 可立即提交当前查询。切换查询或普通/收藏模式增加 generation、清空 items/cursor/错误并滚回顶部。
- 距底部不大于 `480px`、存在 `next_cursor` 且没有追加请求时触发下一页。同一 generation 只允许一个第一页请求和一个追加请求，旧 generation 的成功或失败均忽略。
- 初始失败显示整页重试。成功列表的手动刷新失败保留 items/cursor/滚动位置并显示非阻断重试；追加失败保留 items 与 cursor，只允许局部重试同一 cursor，普通触底不得自动重复失败请求。
- cursor 返回 `validation_failed` 时按当前 query/favorite 重新请求第一页；同一 generation 最多自动恢复一次。
- 收藏按钮在途时禁用同一 ActorId 的重复提交。成功后同步当前详情和已加载列表中的该 ActorId；取消收藏后若当前是收藏模式，从列表移除该项但不伪造下一页。失败保留旧值并提供重试。
- 认证服务端或会话变化必须清空 query、模式、快照、cursor、收藏在途状态和详情状态。

## 3. 路由与任务所有权

- TASK-206 建立 `/app/actors` 与 `/app/actors/:actor_id` typed route；actor_id 必须先通过 UUID 路径段校验。列表项与全局搜索女优结果关闭搜索对话框后进入同一详情路由。
- 女优详情关联影片使用只读 `MovieCard` 展示服务端 `movies`。TASK-206 不创建影片详情占位页、来源选择或播放行为；TASK-207 在其正式范围内接管影片详情路由并把这些卡片接入导航。
- TASK-207 的影片详情演员项必须复用本任务 Actor detail route，不另建按姓名定位的详情入口。

## 4. GFriends URL 与下载

- 唯一允许的资产 URL 是：scheme 为 `https`、host 精确为 `raw.githubusercontent.com`、默认端口、无 userinfo/query/fragment，path 以 `/li-peifeng/gfriends/main/Content/` 开始且不含空、`.`、`..` 或反斜杠段。后端按 TASK-223 变更规格移除持久证据 URL 中已允许的数字 `t` query；客户端不得自行删除 query 或放宽本白名单。
- GFriends 使用独立匿名 Dio 下载器，不复用认证 `ApiClient`，不发送 Authorization、Cookie、refresh token、server base URL凭据或任意业务 header。`ApiClient` 的安全相对路径限制保持不变。
- 下载连接超时 `10s`、接收超时 `30s`，最多 3 次重定向；每一跳都必须重新满足同一 URL 规则。只接受 HTTP 200、最多 `8 MiB` 的完整响应、JPEG/PNG/WebP Content-Type 与对应文件签名。
- 同一 URL 的并发请求 single-flight；全局最多 4 个实际下载。调用者取消后不得写缓存；所有等待者取消时取消底层请求。
- 网络、状态、重定向、超限、格式、解码或取消失败只影响当前图片，不得改变 Actor DTO、列表、收藏或其他缓存命中。

## 5. 文件缓存与生命周期

| 项目 | 固定值 |
|---|---:|
| 目录 | `%LOCALAPPDATA%/SakuraPlayer/cache/gfriends-v1` |
| 最大文件数 | 512 |
| 最大总字节 | 256 MiB |
| 滑动期限 | 成功访问后 7 天 |
| 下载并发 | 4 |
| 单图上限 | 8 MiB |
| 重定向上限 | 3 |

- 缓存索引只保存 URL、应用生成的稳定文件 ID、字节数、格式和 `last_accessed_at`；不得保存 token、Cookie 或服务端认证头。索引和图片使用同目录临时文件后原子替换，启动时删除不在有效索引中的临时/孤立文件。
- 初始化和成功写入后执行整理：先删除过期或缺失项，再按 `last_accessed_at`、文件 ID 升序淘汰，直到文件数与总字节都不超上限。命中完整文件后更新滑动访问时间。
- 退出登录、更换后端或认证运行时重置时，验证目标是 `%LOCALAPPDATA%/SakuraPlayer` 的严格后代且目录名为 `cache/gfriends-v1` 后才可递归删除。正常关闭应用保留未过期项。
- GFriends 清理不得访问或删除后端永久 `catalog-images`、客户端字幕目录或 SakuraPlayer 应用根中的其他路径。索引损坏时只重建 `gfriends-v1`，不得向上扩大清理范围。

## 6. 桌面界面

| 项目 | 数值 |
|---|---:|
| 列表批量 | 24 |
| 搜索防抖 | 300ms |
| 女优卡最小 track | 200px |
| 女优卡高度 | 320px |
| 头像区域高度 | 220px |
| 网格横纵间距 | 16px |
| 普通页面水平内边距 | 24px |
| `<900px` 页面水平内边距 | 16px |
| 追加触发距离 | 480px |

- 列表顶部使用姓名/别名搜索输入、普通/收藏分段模式和刷新命令。女优卡显示头像、显示名、可用中日文名、别名和收藏状态；缺头像和图片失败使用固定占位，长姓名最多两行，别名在固定高度内换行/省略。
- 详情使用无嵌套装饰卡的资料头；中日文名不重复显示相同值，别名自然换行，简介缺失显示稳定空状态。收藏使用图标按钮及 tooltip，在途保持固定尺寸。
- 写真使用实际图片网格。缩略图按需进入全局四并发缓存队列；点击后打开大图查看器，当前图可缩放并可前后切换。查看器只请求当前图，关闭或页面销毁取消不再需要的排队/在途请求。
- 单张写真失败显示固定失败占位和重试，不移除其他写真；无写真显示独立空状态。关联影片按 TASK-204 固定 `MovieCard` 网格展示，不在本任务提供来源或播放动作。

## 7. 验证

- API/Controller：严格 DTO、query/favorite/cursor、generation、迟到响应、刷新/追加保留、游标恢复、收藏幂等/失败和认证清理。
- Cache：URL 每字段、逐跳重定向、响应/格式上限、single-flight、四并发、取消、原子写入、7 天过期、512/256 MiB LRU 和目录隔离。
- Widget/Route：列表/搜索到详情、长文本、缺头像/简介/写真、收藏、写真查看器、关联 MovieCard、加载/空/失败/重试与窄窗口。
