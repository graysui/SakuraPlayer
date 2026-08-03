# Change Specification: 影片详情中文简介与重新刮削

**Type**: Delta
**Date**: 2026-08-03
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

Windows 实际体验中，影片详情简介会同时展示 AI 中文译文与 DMM 原文；详情页也没有直接重新刮削当前番号的入口。本变更新增 TASK-227，在不删除内部原文、不自动批量重试和不改变付费翻译幂等事实的前提下，只向简介主展示投影中文译文，并提供用户显式触发的影片级最高优先级完整刮削。

## ADDED

- REQ-CHG-289：新增 TASK-227，负责影片详情中文简介投影、影片级重新刮削 API 和 Windows 详情交互；TASK-214 增加 TASK-227 依赖并继续保持 pending。
- REQ-CHG-290：`GET /api/v1/movies/{movie_id}` 的 `description` 只投影已持久化的 `description_zh`，没有中文译文时为 null，不得回退 DMM/JavDB 原文。`description_original` 作为兼容字段和内部翻译来源事实保留，但 Windows 简介区不得显示它。
- REQ-CHG-291：新增认证管理员 `POST /api/v1/admin/movies/{movie_id}/metadata-rescrape`。请求不接收番号、provider、阶段或优先级；服务端从 MovieId 读取当前规范化番号并创建或复用 `priority=10, reason=manual_or_search, retry_mode=full` 的任务。
- REQ-CHG-292：影片级重新刮削在 Movie 行锁事务内执行。没有活动任务时基于最新终态创建下一 attempt；已有 queued full attempt 时提升为 priority 10 并复用；已有 running full attempt 时原样复用；已有活动 enrichment-only attempt 时返回 `metadata_job_already_active`，不得把运行中的部分任务改写为完整任务或创建重复活动 attempt。
- REQ-CHG-293：Windows 番号详情资料头提供带刷新图标的“重新刮削”按钮。请求在途时按钮禁用；成功按 `queued/running` 显示中文反馈，失败保留当前详情并显示中文错误。按钮不得触发页面打开即刮削、连续并发请求或任何批量重试。

## MODIFIED

- REQ-CHG-294：AC-040/041/122 的管理员手动重试增加影片详情显式入口；失败不自动重试、固定三槽、600 秒硬超时和 priority 10 最高优先级保持不变。
- REQ-CHG-295：AC-055/057/074 的简介展示增加中文-only 投影。重新刮削可进入既有 translation stage，但相同 source/model/prompt 的 completed/dispatched/unknown/rejected 事实仍按既有业务键复用或拒绝自动重派。

## Unchanged Behavior

- 数据库继续保存 DMM 原文用于 AI 翻译、来源摘要和审计；本变更不删除或改写原文。
- 标题的中日文展示、演员简介、来源、剧照、收藏和播放行为不变。
- 搜索与排行榜自动协调仍不得重试 failed attempt；只有用户点击详情按钮才触发本入口。
- 默认测试不得访问真实 JavDB、DMM、GFriends、115 或付费 AI。

## Acceptance Criteria

- [x] 有中文简介和原文时，详情 `description` 只返回中文，Windows 简介区只出现中文；只有原文时 `description=null` 且显示“暂无中文简介”。
- [x] core-ready、failed 和从未建立 attempt 的影片可由 MovieId 创建下一 full attempt，priority 固定为 10，历史终态保持不可变。
- [x] queued full 被提升并复用，running full 被复用；活动 enrichment-only 返回稳定冲突，不产生第二条活动任务。
- [x] Windows 按钮在途防重，成功和失败均使用中文反馈，失败不清空详情、收藏或来源选择。
- [x] 重新刮削不自动重派旧翻译事实，默认测试保持离线。

## Testing Strategy

- 后端单元测试覆盖中文简介无回退、MovieId/番号绑定、无 attempt、终态、queued/running full 和 enrichment 冲突。
- PostgreSQL/API 测试覆盖认证、priority 10、attempt 递增、活动唯一约束、历史不可变和响应 DTO。
- Windows gateway/controller/widget 测试覆盖认证请求、严格响应、在途防重、中文状态、仅中文简介和详情状态保留。
- Fast/Final 继续使用现有离线测试与 Compose 门禁，不调用真实 provider 或付费 AI。

## Rollback Plan

提交前可整体移除 TASK-227。提交后若需要恢复原文展示，应通过新的前向变更重新定义客户端展示；不得删除数据库原文、历史 metadata attempts 或 translation records。
