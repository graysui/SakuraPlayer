# Change Specification: TASK-205 Windows 排行榜客户端边界

**Type**: Delta
**Date**: 2026-07-30
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-205 的 Definition of Ready 要求榜单 DTO 已生成，但正式创建清单和 Windows 实际工程都表明 `rankings_api.dart` 尚不存在，应由 TASK-205 自身交付。任务还要求复用 TASK-204 的 `MovieCard`，依赖却只写 TASK-203。现有客户端通用错误模型又丢弃 `/rankings` 已冻结的 `details.reason`，无法稳定表达 TOP250 未配置凭据等可操作状态。本变更修正所有权与依赖，并补齐榜单选择、分页、失败保留、错误动作和桌面布局边界，不改变后端 `/rankings` 行为或新增榜单类型。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### Windows 排行榜确定性客户端协议

**Requirements**:

- REQ-CHG-126: TASK-205 拥有 Windows `RankingBoard`、`RankingItem`、`RankingPage`、榜单选择和游标 DTO/API，直接消费已冻结的 `GET /api/v1/rankings`。影片字段必须复用 TASK-204 的 `MovieSummaryDto` 和认证封面读取，不复制或放宽影片摘要协议。
- REQ-CHG-127: 客户端固定请求 `limit=24`。日榜、周榜、月榜不得发送 `year`；TOP250 的总榜省略 `year`，年度榜只发送响应 `available_years` 中的值。切换 board/year 清空旧 cursor、滚回顶部并使用新的请求 generation；迟到成功或失败不得覆盖当前选择。
- REQ-CHG-128: 榜单项按服务端顺序渲染并显示原始正整数 `rank`，允许名次间隙。客户端不得重新判断 AVdb 来源、`core_ready` 或元数据任务状态，也不得直连 JavDB。`synced_at` 显示为服务端快照时间，刷新只重新请求后端。
- REQ-CHG-129: 初始或选择切换失败不显示其他榜单的旧数据；当前成功榜单的手动刷新失败保留既有 items、cursor、synced_at 和滚动位置并显示非阻断重试。追加失败保留既有项与 cursor，只允许局部重试同一 cursor；重复触底只允许一个追加请求。
- REQ-CHG-130: Windows 通用 API 错误模型保留不可变 `details` 对象但不得记录或展示任意原始内容。排行榜只接受 `ranking_snapshot_unavailable` 的固定 reason：`credentials_not_configured`、`credentials_invalid`、`never_synced`、`sync_failed`；未知或畸形 details 降级为普通加载失败。
- REQ-CHG-131: `credentials_not_configured` 与 `credentials_invalid` 显示前往管理员设置的动作；`never_synced` 与 `sync_failed` 显示重新请求本地快照的动作。该错误只影响当前 board/year，不得使其他榜单不可用。
- REQ-CHG-132: 排行榜复用 TASK-204 的 `MovieCard` 可读子集，外层叠加固定 rank 标识。网格继续使用 `184px` 最小 track、`408px` 卡片主轴高度、`16px` 横纵间距和认证封面；普通页面水平内边距为 `24px`，可用宽度小于 `900px` 时为 `16px`，触底阈值为 `480px`。
- REQ-CHG-133: board/year 选择保存在当前认证会话的页面内存状态，离开并返回排行榜可恢复选择；认证服务端或会话变化必须清空选择、快照、cursor 和错误。TOP250 年份控件只在该榜单显示，总榜始终可选，年度选项以服务端 `available_years` 降序为真相。

**Acceptance Criteria**:

- [ ] API 测试覆盖四种 board、year 省略/发送、固定 limit、严格 DTO、rank 间隙、synced_at、共享 MovieSummary 和类型化不可用 details。
- [ ] Controller 测试覆盖选择保留、board/year generation、迟到响应、重复触底、追加局部重试、刷新失败保留和认证会话清理。
- [ ] Widget 测试覆盖四榜单、TOP250 年份、rank、同步时间、认证封面、空/加载/普通失败/四种不可用 reason、追加失败和窄窗口。

**Impact**: AC-046、AC-069 至 AC-073、TASK-205、Windows 通用 API 错误模型、Windows 排行榜客户端契约、功能规格和追踪矩阵；Breaking: NO，后端接口不变且 Windows 排行榜尚未实现。

## MODIFIED

### TASK-205 Definition of Ready、依赖与文件所有权

**Previous Behavior**: TASK-205 要求榜单 DTO 已生成，同时声明自己创建 `rankings_api.dart`；任务要求复用 TASK-204 的 `MovieCard`，依赖却只写 TASK-203。

**New Behavior**: TASK-204 是 TASK-205 的直接依赖并提供 Shell route、`MovieSummaryDto`、认证封面和 `MovieCard`；TASK-205 自身拥有 Ranking DTO/API。选择、年份、分页、错误 details、失败保留和桌面几何由 [Windows 排行榜客户端契约](../contracts/windows-rankings-client.md) 冻结。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-205 DoR/dependency | MODIFIED | LOW |
| Windows API error DTO | MODIFIED | MEDIUM |
| Windows rankings DTO/controller/UI | ADDED | MEDIUM |
| `/rankings` OpenAPI/backend | UNCHANGED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-205 的 AC 映射。变更规格、客户端契约、功能规格、TASK-205 和追踪矩阵先独立提交；TASK-205 实现、测试、状态与交接仍在后续 TASK-205 中文提交中完成。

## Testing Strategy

- Dart 单元测试固定 Ranking 查询编码、DTO、错误 details、generation、刷新和游标状态机。
- Flutter Widget 测试固定选择器、年份、rank、同步时间、网格和错误动作。
- Fast 运行 `dart format`、`flutter analyze` 和完整 `flutter test`；Final 运行 Windows debug build，不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-205 实现提交前可整体回退本变更。实现提交后只能通过新的前向变更调整客户端布局或状态语义，不得让客户端偏离已冻结的 `/rankings` board/year、snapshot cursor、MovieSummary 和不可用 reason 契约。
