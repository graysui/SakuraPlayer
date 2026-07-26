---
id: TASK-013
title: "管理设置、诊断与持久事件"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-002, TASK-003, TASK-007, TASK-011, TASK-012]
ac-mapping: [AC-115, AC-116, AC-119, AC-120, AC-121, AC-122, AC-127, AC-128, AC-129]
imp-requirements: [REQ-021, REQ-022, REQ-023, REQ-024]
cross-boundary: true
external-dependency-risk: false
provides: [domain event log, websocket gateway, REST snapshot, settings diagnostics]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-013: 管理设置、诊断与持久事件

**功能描述**: 建立全局水位事务事件日志、鉴权 WebSocket/有界 REST 快照恢复、对象级 CAS 脱敏设置/连接测试、元数据管理和诊断 API。

**规格映射**: AC-115、AC-116、AC-119 至 AC-122、AC-127 至 AC-129

## 验收条件

- [x] 元数据状态通过全局 sequence、聚合 stream_version 和版本化 WebSocket 推送；有界 REST 快照与事件水位一致。cache/credential 使用空扩展端口，由后续任务填充；对应 AC-115、AC-116。
- [x] 设置 API 以完整对象和 expected_version 原子管理 JavDB/AI，管理 TTL/同步和 typed 连接测试；回显非敏感现值与全量/增量同步状态，但启动级主密钥不可由客户端修改；对应 AC-119、AC-120。
- [x] 诊断使用严格 DTO 显示脱敏 stage、稳定错误码、耗时、尝试和连接结果；管理员可完整重试 failed 任务或显式重试 warning 富化阶段；对应 AC-121、AC-122。
- [x] 健康/恢复状态可观察，无心跳证据的 worker/scheduler 返回 unknown；默认测试使用替身并可运行 Phase 1 已交付关键算法清单，后续算法由 TASK-101/212 负责；对应 AC-127 至 AC-129。

## Definition of Ready

- [x] TASK-002 鉴权、TASK-003 脱敏、TASK-007 元数据管理端口可用。
- [x] realtime-events.md 和 error-codes.md 已冻结。
- [x] cache 事件暂以扩展注册点存在，由 TASK-112 填充。
- [x] `2026-07-26--task-013-events-settings-diagnostics-boundaries.md` 已接受并同步。

## 技术上下文

- 领域状态和 `domain_event` 在同一事务写入；WebSocket 不是状态真相。
- event_id 去重、全局 sequence 追赶、stream_version 聚合合并、30 天保留和 4409 游标过旧按契约处理。
- settings 返回 configured/status，不回显 secret 值。

## Cross-Boundary Warning

本任务在共享事件、身份与配置、目录与元数据之间做应用层聚合。只允许通过 `DomainEventWriter` 和 typed settings/diagnostics port 接入；元数据状态机语义仍归 catalog 所有，API 路由不得直接写领域状态。完整边界见 [TASK-013 事件、设置与诊断确定性边界](../changes/2026-07-26--task-013-events-settings-diagnostics-boundaries.md)。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/events/outbox.py` - 事务事件写入/读取。
- `backend/src/sakuraplayer/events/websocket.py` - 鉴权 WebSocket gateway。
- `backend/src/sakuraplayer/events/snapshot.py` - REST snapshot 聚合和游标。
- `backend/src/sakuraplayer/events/models.py` - 事件 ORM 与空扩展端口类型。
- `backend/alembic/versions/0013_events_settings_diagnostics.py` - 事件/公开设置 Schema。
- `backend/src/sakuraplayer/api/settings.py` - 脱敏设置和连接测试。
- `backend/src/sakuraplayer/api/diagnostics.py` - 诊断与任务管理 API。
- `backend/tests/integration/events/test_reconnect_snapshot.py` - 事件丢失/重连。
- `backend/tests/integration/api/test_settings_diagnostics.py` - secret 和任务操作。
- `backend/tests/integration/api/test_enrichment_retry.py` - warning 阶段白名单与新 attempt。

## 测试说明

**单元测试**:

- 事件全局 sequence、聚合版本、去重、30 天保留、敏感 payload 拒绝和错误码本地化边界。
- 设置 patch 只允许 TTL/JavDB/AI 完整对象 CAS，拒绝主密钥、部分 secret 拼接和固定并发修改。

**集成测试**:

- 事务回滚时无事件；提交后 WebSocket 收到，断线/游标跳号后从一致且每类最多 100 项的 REST 快照恢复。
- 手动重试失败元数据任务、只重试指定富化阶段、连接测试和诊断响应不包含任何秘密。

**边界条件**:

- 过旧游标、访问令牌过期、未知事件类型、连接测试超时、worker 重启状态。

## Definition of Done

- [x] 事件、快照、设置、诊断和元数据管理完成。
- [x] WebSocket/REST 均受认证保护。
- [x] 关键后端自动测试清单可从 CI 运行。

## 验证证据

- 最终 Fast 为 466 passed、7 deselected；compileall、宿主 Docker 配置断言、OpenAPI/迁移静态检查、敏感模式和 `git diff --check` 通过，完整自审无剩余 P0/P1/P2。
- PostgreSQL 覆盖 0013 升降级、全局 sequence/聚合版本并发、事务回滚、过期游标和 Schema head；自包含测试覆盖设置 clear CAS、秘密不回显、诊断 stage、认证 WebSocket 4401/4403/4409 和 100 项快照上限。
- Compose Final 尝试 1 因共享 Schema guard 未加入 0013 表名而结束，迁移本身成功且资源已清理；修复后 Fast/审计重新通过。
- Compose Final 尝试 2 通过后，提交检查发现测试文件末尾空行并使证据失效；修复后 Fast/审计重新通过。最终尝试 3 通过：自包含 466 passed、7 deselected，PostgreSQL 84 passed、15 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启、ready 降级恢复和隔离资源清理全部完成。

**依赖**: TASK-002, TASK-003, TASK-007, TASK-011, TASK-012

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-013.md"`
