# Windows 媒体库客户端契约

**Status**: Accepted
**Date**: 2026-07-30
**Owner**: TASK-204

本契约固定 Windows 媒体库对既有 `/api/v1/movies` 的消费、桌面布局和分页恢复行为。后端过滤与 DTO 真相继续以 `rest-api.openapi.yaml` 和 TASK-011 目录查询变更规格为准。

## 1. API 所有权与查询

- TASK-204 在 `windows/lib/features/library/data/movies_api.dart` 实现 `MovieSummary`、`PlaybackProgress`、`MoviePage`、筛选和 Movies gateway；TASK-203 只提供 `/app/library` Shell route。
- 每页固定 `limit=24`，默认 `sort=publish_date_desc`。
- `categories` 和 `labels` 去重后使用逗号分隔值；空集合不发送。可选参数名严格为 `source_website`、`playable`、`min_resource_size_mb`、`max_resource_size_mb`、`favorite`、`sort` 和 `cursor`。
- 客户端不重新判断 `core_ready`，不按来源重复卡片，不在本地拼接来源条件。后端返回一个 `MovieSummary` 就渲染一张卡片。
- `cover_url` 必须匹配 `/api/v1/catalog/images/{uuid}`，转换为现有 API client 的 `catalog/images/{uuid}` 安全相对路径并携带认证读取。null、格式非法或字节读取失败都显示同尺寸占位图。

## 2. 筛选状态

| 筛选 | 控件语义 | 查询编码 |
|---|---|---|
| 六分类 | 独立多选 | `categories=a,b`；OR 由服务端执行 |
| subtitle/cracked/4k/censored | 独立多选 | `labels=a,b`；AND 由服务端执行 |
| 来源 | 全部/sehuatang/x1080x 单选 | `source_website` |
| 可播放 | 全部/可播放/未就绪三态 | `playable` 省略/true/false |
| 大小 | 非负整数 MiB 最小/最大 | 两个 size 参数；min 大于 max 不发请求并显示本地校验 |
| 收藏 | 独立布尔开关 | 仅 true 时发送 `favorite=true` |
| 排序 | 发布日期新到旧/旧到新/番号 | 对应三个 OpenAPI sort 值 |

筛选与滚动位置仅是当前页面内存状态。任何筛选变化都清空 items/cursor/追加错误、滚回顶部并发起新的第一页请求。

## 3. 固定桌面几何

| 项目 | 数值 |
|---|---:|
| 初始与追加批量 | 24 |
| 海报宽高比 | 2:3 |
| 最小网格 track | 184px |
| 网格横纵间距 | 16px |
| 卡片主轴高度 | 408px |
| 筛选内容最大宽度 | 1180px |
| 普通页面水平内边距 | 24px |
| `<900px` 页面水平内边距 | 16px |
| 追加触发距离 | 距底部 480px |

网格列数按当前内容可用宽度、最小 track 和间距计算，至少一列。卡片中的占位图、图片、标签、标题、进度和加载状态必须位于固定几何内，不得改变 track 或卡片高度。

## 4. 进度显示

- `progress=null`：播放按钮显示“播放”，不显示百分比。
- `completed=true`：显示已看完状态；不使用 position 计算百分比。
- `completed=false && duration_seconds>0`：显示 `position/duration` 的百分比并夹在 0% 至 100%。
- `completed=false && duration_seconds=null`：显示已播放时长，不计算百分比。
- UI 只消费服务端权威进度；TASK-204 不写进度，后续 TASK-211 负责播放期间刷新。

## 5. 分页与恢复

- 初始请求与追加请求各自最多一个在途操作。滚动距底部不大于 480px、存在 `next_cursor` 且没有追加操作时才能触发。
- 每次筛选变化增加 generation；不属于当前 generation 的响应和错误全部忽略。
- 追加成功只追加服务器返回项并替换 `next_cursor`；不在客户端按来源去重。测试 fixture 若包含重复 movie ID，视为协议/fixture 缺陷，UI 仍以 movie ID key 保持单卡身份。
- 追加失败保留 items、cursor 和滚动位置，局部重试使用同一 cursor。初始失败不伪造空结果。
- 服务端对 cursor 返回 `validation_failed` 时清空旧 cursor 并重新加载当前筛选第一页；同一 generation 最多自动恢复一次，避免循环。

## 6. 验证

- API/DTO：默认与完整查询、空参数、枚举、日期、UUID、labels、progress、next cursor、认证图片路径。
- Controller：初始/空/追加、快速筛选、迟到响应、重复触底、游标恢复、局部重试。
- Widget：固定网格、窄窗口、长标题、缺图/失败、进度/完成、加载和错误状态。
