# Change Specification: TASK-206 Windows 女优客户端边界

**Type**: Delta
**Date**: 2026-07-30
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-206 的 Definition of Ready 要求本地图片 cacheDir、LRU/过期策略和占位资源已确定，但冻结规格只要求“有界临时缓存”，没有给出目录、容量、期限、下载安全、取消或会话清理规则。任务还要求复用 TASK-204 的 `MovieCard`，依赖却只写 TASK-203；测试说明中的“关联影片导航”又会提前侵占 TASK-207 明确拥有的影片详情路由。本变更修正依赖与任务所有权，并补齐 Actor DTO、分页、收藏、路由、GFriends 下载缓存、失败隔离和桌面布局边界，不改变后端 `/actors`、GFriends 唯一匹配或影片详情行为。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### Windows 女优确定性客户端协议

**Requirements**:

- REQ-CHG-134: TASK-206 拥有 Windows `ActorSummary`、`ActorDetail`、`ActorPage` 和 Actors gateway，直接消费已冻结的 `GET /api/v1/actors`、`GET /api/v1/actors/{actor_id}` 与幂等 `PUT/DELETE /favorite`。关联影片必须复用 TASK-204 的严格 `MovieSummaryDto`、认证封面 loader 和 `MovieCard`，不得复制或放宽影片摘要协议。
- REQ-CHG-135: 女优列表固定请求 `limit=24`，姓名/别名查询去除首尾空白后为 1 至 200 个字符；空查询省略 `q`。普通与收藏视图分别省略 `favorite` 或发送 `favorite=true`。切换查询/收藏模式必须增加 generation、清空 cursor 并滚回顶部，迟到成功或失败不得覆盖新范围。
- REQ-CHG-136: 列表触底、追加失败保留、刷新保留、单次游标失效恢复和认证会话清理遵循 [Windows 女优客户端契约](../contracts/windows-actors-client.md)。收藏操作只使用 ActorId 和幂等 PUT/DELETE；请求失败保留权威旧状态，不从显示名称推断身份或收藏。
- REQ-CHG-137: TASK-206 建立 `/app/actors` 与 `/app/actors/:actor_id` typed route，并把全局搜索与列表项接到女优详情。关联影片在本任务只显示只读 `MovieCard`；影片详情、来源选择及其路由继续由 TASK-207 实现，TASK-206 不建立占位影片详情或播放行为。
- REQ-CHG-138: `profile_url` 和 `gallery_urls` 只接受无 userinfo、query、fragment 和非默认端口的 `https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/` URL。匿名图片下载不得复用认证 `ApiClient`、发送 Authorization/Cookie 或放宽其安全相对路径限制；最多 3 次重定向且每跳重新验证同一边界，响应正文最多 8 MiB并只接受 JPEG、PNG 或 WebP 声明与文件签名。
- REQ-CHG-139: Windows GFriends 缓存固定为 `%LOCALAPPDATA%/SakuraPlayer/cache/gfriends-v1`，不得进入永久目录图片或字幕目录。缓存最多 512 个完整文件且总计最多 256 MiB，成功访问后滑动保留 7 天；整理时先删除过期项，再按 `last_accessed_at`、稳定文件 ID 淘汰最久未访问项。文件和索引必须使用同目录临时文件后原子替换，半文件、失败响应和无效图片不得进入索引。
- REQ-CHG-140: 同一 URL 的并发请求复用单次下载，所有 GFriends 下载全局最多 4 个；写真缩略图按可见需要加载，查看器只按需加载当前大图。页面或查看器销毁必须取消尚未需要的排队/在途请求。单图失败仅显示占位与显式重试，不清空成功列表、详情或其他缓存命中。
- REQ-CHG-141: 退出登录、更换后端或认证运行时重置时，只能在证明目标位于 SakuraPlayer 应用私有根下后清空 `gfriends-v1`；正常进程退出保留未过期缓存。清理不得删除永久目录图片、字幕或应用根的其他内容。
- REQ-CHG-142: 女优列表使用固定响应式网格：最小 track `200px`、卡片主轴高度 `320px`、头像区域 `220px`、横纵间距 `16px`；页面水平内边距在可用宽度小于 `900px` 时为 `16px`，否则为 `24px`，触底阈值为 `480px`。长姓名最多两行，别名在固定区域换行/省略，不改变卡片几何。
- REQ-CHG-143: 女优详情使用无嵌套装饰卡的资料头、别名/简介、写真网格与关联影片网格；缺头像、简介或写真分别显示稳定占位。写真查看器支持当前图的缩放、前后切换、加载/失败/重试和关闭；收藏在途禁用重复提交，成功后同步当前详情及已加载列表状态。

**Acceptance Criteria**:

- [ ] API/DTO 测试覆盖查询、收藏分页、严格字段/集合上限、ActorId、幂等收藏和共享 MovieSummary。
- [ ] Controller 测试覆盖查询防抖输入、scope generation、迟到响应、重复触底、追加/刷新保留、游标恢复、收藏失败与认证会话清理。
- [ ] 缓存测试覆盖精确 URL、重定向、8 MiB/格式边界、同 URL 单飞、四并发、过期/LRU、原子失败、取消和安全清理隔离。
- [ ] Widget/路由测试覆盖全局搜索与列表到详情、长别名、缺头像/简介/写真、收藏、写真查看器、关联 MovieCard 和窄窗口。

**Impact**: AC-051 至 AC-053、AC-075 至 AC-077、TASK-206、TASK-207 的路由所有权、Windows 女优客户端契约、功能规格、任务索引和追踪矩阵；Breaking: NO，后端接口不变且 Windows 女优页面尚未实现。

## MODIFIED

### TASK-206 Definition of Ready、依赖与导航所有权

**Previous Behavior**: TASK-206 依赖 TASK-203，却要求复用 TASK-204 的 `MovieCard`；cacheDir、LRU/过期、下载安全和失败恢复没有可执行数值；测试说明要求关联影片导航，但 TASK-207 才拥有影片详情。

**New Behavior**: TASK-204 是 TASK-206 的直接依赖并提供 Shell、`MovieSummaryDto`、认证封面和 `MovieCard`；TASK-206 自身拥有 Actor DTO/API、列表/详情路由和 GFriends 临时缓存。关联影片在本任务只显示，TASK-207 后续接管影片详情导航；缓存、分页、收藏和布局由 [Windows 女优客户端契约](../contracts/windows-actors-client.md) 冻结。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-206 DoR/dependency | MODIFIED | LOW |
| Windows Actor DTO/controller/routes/UI | ADDED | MEDIUM |
| Windows GFriends cache/downloader | ADDED | HIGH |
| `/actors` OpenAPI/backend | UNCHANGED | LOW |
| TASK-207 movie detail ownership | UNCHANGED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-206 的 AC 映射。变更规格、客户端契约、功能规格、Windows 任务索引、TASK-206 和追踪矩阵先独立提交；TASK-206 实现、测试、状态与交接仍在后续 TASK-206 中文提交中完成。

## Testing Strategy

- Dart 单元测试固定 Actor 查询/DTO、收藏、generation、游标和 GFriends 文件缓存状态机。
- Flutter Widget/路由测试固定列表、详情、全局搜索导航、写真查看器、占位、长文本和响应式网格。
- Fast 运行 `dart format`、`flutter analyze` 和完整 `flutter test`；Final 运行 Windows debug build，不访问真实 GFriends、115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-206 实现提交前可整体回退本变更。实现提交后只能通过新的前向变更调整客户端缓存或布局语义，不得让客户端自行匹配姓名、放宽 GFriends URL、混用永久目录图片缓存或侵占 TASK-207 影片详情所有权。
