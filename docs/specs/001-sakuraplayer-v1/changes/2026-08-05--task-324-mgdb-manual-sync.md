# Change Specification: TASK-324 MGDB 手动同步

**Type**: Delta
**Date**: 2026-08-05
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

管理员保存 MGDB 数据源只更新加密配置，不会创建同步请求。如果 scheduler 首次全量请求已经因未配置来源失败，后续保存来源也不会补建请求，Windows 同步状态会继续停留在失败或从未同步。本变更增加受认证的手动全量同步请求和 Windows“设置 - 同步状态”入口，让管理员在确认来源后显式开始同步。

## MODIFIED

- AC-119：Windows 设置页继续显示 MGDB 30D 增量和全量校对状态，并在同步区增加单个“立即全量同步”按钮；保存数据源本身不隐式触发同步。
- Windows 设置契约原“不增加手动同步入口”边界改为只允许管理员显式创建 MGDB `full_reconcile` 请求；不提供手动增量、任意模式或外部资源输入。

## ADDED

- AC-150 / REQ-CHG-311：受认证管理员可通过 `POST /settings/mgdb-sync-requests` 创建一次 MGDB 全量校对请求。未配置来源返回 `mgdb_source_not_configured` 且不入队；同模式已有 `queued/claimed` 请求时复用该活动请求，只有终态请求时使用下一个空闲分钟槽新建请求并保留终态审计记录。响应只返回请求 UUID、固定模式和 `created`，不包含来源内容或磁力。
- Windows 请求在途时禁用按钮；成功后显示“全量同步请求已提交”并刷新 Settings 真相，失败保留原同步状态并按稳定错误码显示中文。未配置 MGDB 时按钮禁用。

## Scope And Safety

- 复用现有 `AvdbSyncQueue`、worker 和数据库唯一约束，不新增迁移。
- 保留每日 03:00 的 30D 增量、每周日 04:00 的全量校对和 worker 幂等导入语义。
- 不自动访问真实 MGDB；默认测试使用本地数据库和 HTTP/UI 替身。
- 不改变 MGDB URL 白名单、Release 校验、解密、磁力加密保存或客户端秘密边界。

## Task Synchronization

新增独立 `TASK-324`，依赖 TASK-215 和 TASK-315。同步更新功能规格、OpenAPI、错误码、Windows 设置契约、任务索引、追踪矩阵和交接文档。

## Testing Strategy

- Backend Focused：认证、未配置拒绝、配置后创建 full 请求、活动请求复用、同分钟终态请求不阻断新请求和安全响应。
- Windows Focused：严格响应 DTO、gateway 路径、controller in-flight/成功刷新/失败保留，以及未配置禁用和成功反馈 widget。
- Final：受影响后端测试、Flutter analyze/test、Windows release build 和仓库要求的最终门禁；默认不访问真实外部服务。

## Rollback Plan

实现提交前可整体回退本变更。实现后应通过新的前向 Delta 调整手动同步语义；回滚不得删除已创建的同步请求或既有导入数据。
