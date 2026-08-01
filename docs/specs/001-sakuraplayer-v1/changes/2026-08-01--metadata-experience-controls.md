# Change Specification: 元数据失败详情与队列控制

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

真实使用发现：精确番号搜索命中 raw 影片且元数据补全失败时，Windows 只显示不可点击的失败占位，管理员无法查看已有来源；诊断页也没有暂停和恢复元数据领取的控制。本变更新增 TASK-218，在不放宽媒体库/排行榜正式可见性、不自动重试失败任务和不中断运行中任务的前提下补齐这两个管理闭环。

## ADDED

- REQ-CHG-236: 搜索 `pending_metadata` 项返回稳定 `movie_id`。queued/running/failed 项均可从搜索进入同一影片详情路由；该能力不把影片加入正式搜索影片组、媒体库、排行榜或演员关联影片。
- REQ-CHG-237: `/movies/{movie_id}` 对存在 active identified/manual 来源的非 `core_ready` 影片返回受限待补全详情，显式包含 `metadata_state=queued/running/failed` 与可空稳定 `metadata_error_code`。受限详情只使用 AVdb 影片/来源安全字段，不伪造 JavDB 核心、演员、标签、永久图片、收藏或播放进度事实。
- REQ-CHG-238: Windows 受限详情显示“资料排队中/正在补全资料/资料补全失败”的中文状态和稳定错误映射；隐藏收藏操作，保留已有来源选择及后续缓存/播放入口。正式详情保持现有布局和收藏行为。
- REQ-CHG-239: 新增持久单例 `metadata_worker_control`，管理员可暂停或恢复新任务领取。暂停只阻止新的 claim，不终止、回滚或超时已有 running attempt；恢复只允许后续 claim，不创建任务、不改变优先级且不自动重试 failed attempt。
- REQ-CHG-240: pause/resume 与 metadata claim 复用同一个 PostgreSQL advisory transaction lock；控制请求提交后，任何更晚取得该锁的 claim 必须观察到最新 paused 状态。诊断 `queues.metadata_paused` 是 Windows 控制真相。
- REQ-CHG-241: 新增认证管理员 `PUT /api/v1/admin/metadata-queue`，请求 `{paused:boolean}`，响应返回 `paused/queued/running`。Windows 按钮在途禁用，成功后刷新 diagnostics；不新增 WebSocket 事件。

## MODIFIED

- REQ-CHG-242: AC-066/067 增加 pending `movie_id` 与受限待补全详情例外；“正式影片卡片和详情”仍只属于 `core_ready`。
- REQ-CHG-243: AC-121/122 增加持久 paused 诊断和管理员开始/暂停领取；逐任务 retry、三槽并发、600 秒硬超时与失败不自动重试语义保持不变。
- REQ-CHG-244: TASK-214 增加 TASK-218 依赖；TASK-217 与热更新任务不并入 TASK-218。

## Acceptance Criteria

- [x] pending 搜索项含 movie_id 且 queued/running/failed 均可进入受限详情；正式列表仍只显示 core_ready。
- [x] 受限详情明确返回元数据状态/错误，不允许收藏，且只公开已有安全来源与 AVdb 基础字段。
- [x] pause 提交后不再领取新任务且不打断 running；resume 后可继续按既有优先级领取，failed 不自动重试。
- [x] diagnostics 和 Windows 按钮准确显示 paused 状态，按钮在途禁用且成功后刷新权威快照。

## Testing Strategy

- 后端 Focused 覆盖搜索 DTO、受限详情、收藏边界、迁移、pause/claim 锁顺序、诊断和认证 API。
- Windows Focused 覆盖严格 DTO、pending 导航、三种受限状态、收藏隐藏、开始/暂停按钮及在途/失败恢复。
- Fast/Final 按统一实施流程运行；默认测试不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

只能通过新的前向变更调整受限详情或队列控制语义；不得删除已迁移的控制事实、放宽正式列表可见性或恢复失败任务自动重试。
