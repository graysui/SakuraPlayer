# Windows 排行榜客户端契约

**Status**: Accepted
**Date**: 2026-07-30
**Owner**: TASK-205

本契约固定 Windows 排行榜对既有 `/api/v1/rankings` 的消费、桌面布局和失败恢复行为。后端不可变快照、过滤、元数据排队与 cursor 真相继续以 `rest-api.openapi.yaml` 和 TASK-012 排行榜变更规格为准。

## 1. API 所有权与 DTO

- TASK-205 在 `windows/lib/features/rankings/data/rankings_api.dart` 实现 `RankingBoard`、`RankingItem`、`RankingPage`、选择与 Rankings gateway；TASK-204 提供 Shell route、`MovieSummaryDto`、认证封面 loader 和 `MovieCard`。
- 每页固定 `limit=24`。`board` 必须是 `daily`、`weekly`、`monthly` 或 `top250`；日/周/月不发送 `year`，TOP250 总榜不发送 `year`，年度榜发送服务端 `available_years` 中的整数。
- `RankingPage` 严格读取 `board`、可空 `year`、降序且唯一的 `available_years`、UTC `synced_at`、最多 100 个 items 和可空 `next_cursor`。响应 board/year 必须与请求一致。
- `RankingItem.rank` 必须为正整数，允许间隙；`movie` 必须使用 TASK-204 的严格 `MovieSummaryDto`。客户端不自行过滤来源、`core_ready` 或元数据状态。
- 页面、DTO 和测试不得包含 JavDB HTTP 客户端；打开和刷新页面只调用 SakuraPlayer 后端。

## 2. 选择与本机状态

| 选择 | 页面行为 | 查询编码 |
|---|---|---|
| 日榜 | 隐藏年份 | `board=daily` |
| 周榜 | 隐藏年份 | `board=weekly` |
| 月榜 | 隐藏年份 | `board=monthly` |
| TOP250 总榜 | 显示年份控件并选总榜 | `board=top250`，省略 `year` |
| TOP250 年度榜 | 显示年份控件并选服务端可用年份 | `board=top250&year=YYYY` |

- 初始选择为日榜。board/year 保存在当前认证会话的 Riverpod 页面状态中；离开并返回排行榜时保留选择和当前成功快照。
- 切换 board 时清空 year；切换到 TOP250 后总榜优先。TOP250 成功响应的 `available_years` 是年度选项唯一真相，按服务端降序展示。
- 切换 board/year 时滚回顶部、清空旧 items/cursor/错误并请求第一页。认证服务端或会话变化时清空全部状态。

## 3. 分页、刷新与并发

- 每个选择 generation 最多一个初始/刷新请求和一个追加请求。切换 board/year 增加 generation，旧 generation 的成功或失败均忽略。
- 距底部不大于 `480px`、存在 `next_cursor` 且无追加请求时触发下一页。追加成功保持 rank/影片顺序并替换 cursor；不得按本地 rank 或影片重新排序。
- 追加失败保留 items、cursor、synced_at 和滚动位置，只显示局部重试；普通触底不得在 append error 后自动重试。
- 当前成功榜单的手动刷新在途时保留现有内容；失败继续保留 items、cursor 和 synced_at，并显示可重试提示。初始加载或选择切换失败不得显示其他 scope 的旧数据。
- cursor 返回 `validation_failed` 时按当前 board/year 重新请求第一页；同一 generation 最多自动恢复一次。

## 4. 不可用状态

Windows 通用 `ApiErrorBody`/`ApiException` 保留不可变 details 对象，但业务层只读取已知字段，不记录或展示任意原始 details。

| reason | 页面文案语义 | 动作 |
|---|---|---|
| `credentials_not_configured` | TOP250 尚未配置 JavDB 凭据 | 前往管理员设置 |
| `credentials_invalid` | JavDB 凭据已失效 | 前往管理员设置 |
| `never_synced` | 当前榜单尚未生成快照 | 重新加载 |
| `sync_failed` | 当前榜单最近同步失败且没有可用快照 | 重新加载 |

- 只有 HTTP 503、code 为 `ranking_snapshot_unavailable` 且 reason 在固定集合内时才进入对应不可用状态。
- 未知、缺失或类型错误的 details 视为 `client_protocol_error` 或普通加载失败，不猜测凭据状态。
- 当前 scope 的不可用或网络错误不得改变其他榜单；客户端不触发上游同步，只重新读取后端本地状态。

## 5. 桌面布局

| 项目 | 数值 |
|---|---:|
| 初始与追加批量 | 24 |
| 最小网格 track | 184px |
| 网格横纵间距 | 16px |
| 卡片主轴高度 | 408px |
| 普通页面水平内边距 | 24px |
| `<900px` 页面水平内边距 | 16px |
| 追加触发距离 | 距底部 480px |

- 榜单卡使用 TASK-204 `MovieCard` 的海报、标签、标题、来源、进度和认证封面行为；rank 作为外层固定角标，不改变卡片高度。
- 页面顶部使用四项分段选择；年份只在 TOP250 显示。窄窗口可横向滚动选择器，不允许控件或文本溢出。
- `synced_at` 显示为本地可读快照时间；加载、空、不可用、普通失败、刷新提示和追加失败互不冒充。

## 6. 验证

- API/DTO：四 board、year、limit、响应 scope、available years、synced_at、rank、MovieSummary、cursor 和不可用 details。
- Controller：选择保留、会话清理、迟到响应、重复触底、刷新保留、追加重试和 cursor 恢复。
- Widget：四榜单、TOP250 年份、rank、同步时间、认证封面、空/错误动作、固定网格和窄窗口。
