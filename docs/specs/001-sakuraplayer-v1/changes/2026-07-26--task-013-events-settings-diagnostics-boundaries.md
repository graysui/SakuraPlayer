# Change Specification: TASK-013 事件、设置与诊断确定性边界

**Type**: Delta
**Date**: 2026-07-26
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-013 实施预审发现：UUID 事件游标没有全局顺序，REST 恢复快照无容量上界，设置 PATCH 与既有单载荷 CAS 不一致，Phase 1 又尚无 115 业务端口和跨容器心跳事实。本变更冻结这些实现边界，不新增 Phase 2 的 115、缓存或播放行为。

## ADDED

### 全局事件水位与有界恢复

**Requirements**:

- REQ-CHG-101: `domain_event.sequence` 是数据库生成的全局单调 `bigint`，用于断线追赶和快照水位；`event_id` 仍为全局唯一 UUID，只用于去重和外部游标句柄；`stream_version` 仍是同 `stream + aggregate_id` 的聚合级单调版本，其持久水位独立于 30 天事件正文，清理后不得重置。
- REQ-CHG-102: `after_event_id` 必须先解析为仍保留事件的 `sequence`，按 `sequence ASC` 发送后续事件。游标不存在或已过 30 天保留窗口时关闭 4409。事件写入时固定 `expires_at=occurred_at+30 days`；清理只删除已过期事件。
- REQ-CHG-103: REST 快照在同一数据库事务中先取得当前最大事件 sequence，再读取业务状态，并以该值作为 `snapshot_version`；`last_event_id` 是该水位对应事件。客户端应用快照后只接受 sequence 更大的事件。
- REQ-CHG-104: Phase 1 快照最多返回 100 条元数据任务，优先活动任务、再按更新时间返回最近终态，并同时返回各状态汇总计数。cache、credential 和 notification 由有界扩展端口提供；TASK-112 接入后每类仍最多 100 项。快照不是无限历史导出接口。

### 事务事件端口与 Phase 1 扩展

**Requirements**:

- REQ-CHG-105: TASK-013 可以通过显式 `DomainEventWriter` 端口修改既有元数据事务写路径。状态写入与事件插入使用同一个 SQLAlchemy `Session`；禁止提交后补扫、独立事务或 best-effort 事件。
- REQ-CHG-106: TASK-013 发布元数据 queued/started/stage_changed/completed/failed 事件。cache 与 cloud115 credential 在 Phase 1 使用空快照/无绑定端口，不创建 cache 或 binding 表；TASK-112/102 后续在自己的领域事务内接入同一事件端口。
- REQ-CHG-107: `domain_event.stream` 固定允许 `metadata/cache/credential/catalog/notification`。唯一版本键为 `(stream, aggregate_id, stream_version)`。

### 设置 CAS、连接测试和诊断真相

**Requirements**:

- REQ-CHG-108: `/settings` 对 JavDB 与 AI 使用对象级 replace/clear 命令，命令必须携带 `expected_version`。replace 必须提交完整单载荷字段；clear 使用 CAS 删除整条载荷。字段省略表示不修改，禁止把多个请求版本的字段拼接成新配置。
- REQ-CHG-109: 设置响应回显 JavDB 用户名、AI base URL/model/timeout、配置版本和 secret configured 布尔值；不返回密码、API key、密文、摘要或启动级 secret。缓存 TTL 是非敏感公开设置，范围仍为 1..168 小时。
- REQ-CHG-110: 连接测试通过注入的 typed probe 执行，响应只含 target/status/error_code/elapsed_ms/checked_at。未配置返回 `not_configured`；未交付的 cloud115 probe 在 Phase 1 同样返回 `not_configured`，不得提前访问真实 115。默认测试只用 fake probe。
- REQ-CHG-111: API 可以直接探测自身与 PostgreSQL；没有持久心跳事实时，scheduler/worker 诊断必须返回 `unknown`，不得根据容器假设伪造 healthy。TASK-112 若增加持久心跳，需另行冻结 stale 阈值后再升级状态。
- REQ-CHG-112: TASK-013 对 AC-129 的贡献只证明 Phase 1 已实现的 AVdb、番号、标签、元数据超时和优先级测试清单可由当前测试入口运行；缓存、安全删除、签名、播放进度和字幕生命周期继续由 TASK-101/212 及后续任务交付。

## MODIFIED

### TASK-013 边界与文件所有权

TASK-013 标记为跨边界聚合任务。事件模块拥有 event log、游标和快照协调；身份与配置拥有设置载荷；目录与元数据拥有任务状态。API 路由只调用应用服务。任务索引不再禁止 TASK-013 通过显式端口修改元数据事务文件。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| domain event log / WebSocket / snapshot | ADDED | HIGH |
| settings and diagnostics DTO | MODIFIED | HIGH |
| metadata transaction event port | MODIFIED | HIGH |
| Phase 1 cache/credential extension | ADDED | MEDIUM |

## Task Synchronization

功能规格、架构、技术计划、数据模型、OpenAPI、实时事件、TASK-013、TASK-112、任务索引和追踪矩阵在 TASK-013 同一提交中同步。AC 映射不变；本变更不创建独立 `TASK-CHG`。

## Testing Strategy

- SQLite 自包含测试覆盖事件版本、敏感 payload、设置 CAS、快照容量、认证 WebSocket 和 fake probe。
- PostgreSQL 测试覆盖 0013 迁移、全局 sequence、同聚合并发版本、事务回滚无事件、快照水位和过期游标。
- Fast 运行现有 Phase 1 关键算法清单；Final 使用隔离 Compose，不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-013 提交前可整体回退本变更和实现。提交后事件 sequence、设置 CAS 或公开 DTO 只能通过前向迁移和新版本契约调整。
