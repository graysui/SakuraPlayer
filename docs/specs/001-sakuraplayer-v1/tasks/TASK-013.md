---
id: TASK-013
title: "管理设置、诊断与持久事件"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-002, TASK-003, TASK-007, TASK-011, TASK-012]
ac-mapping: [AC-115, AC-116, AC-119, AC-120, AC-121, AC-122, AC-127, AC-128, AC-129]
imp-requirements: [REQ-021, REQ-022, REQ-023, REQ-024]
cross-boundary: false
external-dependency-risk: false
provides: [domain event log, websocket gateway, REST snapshot, settings diagnostics]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-013: 管理设置、诊断与持久事件

**功能描述**: 建立事务内事件日志、鉴权 WebSocket/REST 快照恢复、脱敏设置/连接测试、元数据管理和诊断 API。

**规格映射**: AC-115、AC-116、AC-119 至 AC-122、AC-127 至 AC-129

## 验收条件

- [ ] 元数据、缓存、凭据状态可通过版本化 WebSocket 推送，客户端重连可用 REST 快照恢复；对应 AC-115、AC-116。
- [ ] 设置 API 管理 115/JavDB/AI/TTL/同步和连接测试，回显非敏感现值与全量/增量同步状态，但启动级主密钥不可由客户端修改；对应 AC-119、AC-120。
- [ ] 诊断使用严格 DTO 显示脱敏 stage、稳定错误码、耗时、尝试和连接结果；管理员可完整重试 failed 任务或显式重试 warning 富化阶段；对应 AC-121、AC-122。
- [ ] 健康/恢复状态可观察，默认测试使用替身并覆盖规格列出的后端关键算法；对应 AC-127 至 AC-129。

## Definition of Ready

- [ ] TASK-002 鉴权、TASK-003 脱敏、TASK-007 元数据管理端口可用。
- [ ] realtime-events.md 和 error-codes.md 已冻结。
- [ ] cache 事件暂以扩展注册点存在，由 TASK-112 填充。

## 技术上下文

- 领域状态和 `domain_event` 在同一事务写入；WebSocket 不是状态真相。
- event_id 去重、stream_version 跳号和 4409 游标过旧按契约处理。
- settings 返回 configured/status，不回显 secret 值。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/events/outbox.py` - 事务事件写入/读取。
- `backend/src/sakuraplayer/events/websocket.py` - 鉴权 WebSocket gateway。
- `backend/src/sakuraplayer/events/snapshot.py` - REST snapshot 聚合和游标。
- `backend/src/sakuraplayer/api/settings.py` - 脱敏设置和连接测试。
- `backend/src/sakuraplayer/api/diagnostics.py` - 诊断与任务管理 API。
- `backend/tests/integration/events/test_reconnect_snapshot.py` - 事件丢失/重连。
- `backend/tests/integration/api/test_settings_diagnostics.py` - secret 和任务操作。
- `backend/tests/integration/api/test_enrichment_retry.py` - warning 阶段白名单与新 attempt。

## 测试说明

**单元测试**:

- 事件版本、去重、敏感 payload 拒绝和错误码本地化边界。
- 设置 patch 只允许 TTL/JavDB/AI 字段，拒绝主密钥和固定并发修改。

**集成测试**:

- 事务回滚时无事件；提交后 WebSocket 收到，断线/游标跳号后 REST 快照恢复。
- 手动重试失败元数据任务、只重试指定富化阶段、连接测试和诊断响应不包含任何秘密。

**边界条件**:

- 过旧游标、访问令牌过期、未知事件类型、连接测试超时、worker 重启状态。

## Definition of Done

- [ ] 事件、快照、设置、诊断和元数据管理完成。
- [ ] WebSocket/REST 均受认证保护。
- [ ] 关键后端自动测试清单可从 CI 运行。

**依赖**: TASK-002, TASK-003, TASK-007, TASK-011, TASK-012

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-013.md"`
