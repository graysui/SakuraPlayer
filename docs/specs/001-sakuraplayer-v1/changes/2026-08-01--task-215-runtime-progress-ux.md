# Change Specification: TASK-215 首次同步与聚合进度体验

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-213 后的真实首次体验发现：新部署只等待定时 30D/全量任务，设置页无法显示 AVdb 已导入数量，诊断页按 24 条分页铺开元数据任务且直接显示英文稳定状态。用户确认首次部署应先建立全量基线，元数据区域只显示总体进度和当前刮削番号。本变更新增 TASK-215，在 TASK-214 清理前修复这些行为，不改变元数据并发、超时或逐任务管理 API。

## ADDED

- REQ-CHG-218: scheduler 启动时，如果数据库从未存在任何 `full_reconcile` request/run，则幂等排入一次首次全量；已有 queued/claimed/completed/failed 全量事实时不得重复排入。后续继续按每天 03:00 的 30D 与周日 04:00 的全量调度。
- REQ-CHG-219: `SyncRunState` 输出当前/最近 run 的 `imported_count`，定义为该 run 已成功 upsert 的 `inserted + updated` 来源行数；`never` 为 0，running 随持久 stats 单调更新，completed 保留最终值。
- REQ-CHG-220: diagnostics 输出 `metadata_progress`：total、queued、running、completed、failed、finished 与最多 3 个当前 running 番号。`completed` 包含 completed 与 completed_with_warnings，`finished=completed+failed`，百分比由客户端按 `finished/total` 计算；total 为当前持久 metadata job 数。
- REQ-CHG-221: Windows 诊断页不再请求或展示元数据逐任务分页、状态、阶段、错误长列表或队列明细；元数据区域只显示总体进度、完成/总数和当前最多 3 个刮削番号。既有逐任务管理 API 保持兼容，不从 OpenAPI 删除。
- REQ-CHG-222: Windows 设置与诊断页对 provider、连接测试、同步和稳定错误码使用统一中文显示映射；未知值显示“未知”，协议层仍严格保留英文稳定枚举和值，不修改服务端错误码。

## MODIFIED

- REQ-CHG-223: AC-020/021 增加首次部署全量基线语义；AC-119/121 增加 AVdb 导入计数与元数据聚合进度；AC-122 的逐任务重试 API 保留，但 Windows 主诊断视图不再列出全部任务。
- REQ-CHG-224: TASK-214 依赖 TASK-215，清理不得提前于本次体验修复。

## Acceptance Criteria

- [ ] 无全量事实的 scheduler 首次启动只排入一次 full；重启或已有任意全量事实时不重复排入。
- [ ] settings 对 never/running/completed/failed 返回可靠非负 imported_count。
- [ ] diagnostics 聚合计数守恒，current_numbers 只来自 running 且最多 3 个、不重复。
- [ ] Windows 诊断页只显示聚合进度和当前番号，不调用 metadata jobs 分页；设置/诊断可见状态均使用中文映射。

## Testing Strategy

- 后端 Focused 覆盖首次排队幂等、sync stats 投影、diagnostics 聚合与 OpenAPI 契约。
- Windows Focused 覆盖严格 DTO、controller 单请求、进度边界、当前番号和中文 Widget 文案。
- Fast/Final 按统一实施流程运行，不访问真实 JavDB 写操作、付费 AI 或真实 115。

## Rollback Plan

只能通过新的前向变更恢复逐任务 Windows 列表或调整首次同步语义；不得删除既有管理 API、同步事实或稳定错误码。
