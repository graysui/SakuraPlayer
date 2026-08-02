---
id: TASK-224
title: "WebSocket 运行依赖修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-013]
ac-mapping: [AC-115, AC-116]
imp-requirements: [REQ-021]
cross-boundary: false
external-dependency-risk: false
provides: [runtime WebSocket protocol implementation]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-224: WebSocket 运行依赖修复

**功能描述**: 修复 API 运行镜像缺少 WebSocket 协议实现导致 Uvicorn 将事件升级请求按普通 HTTP 处理并返回 404 的问题。

**实施边界**: [WebSocket 运行依赖补齐](../changes/2026-08-02--websocket-runtime-dependency.md)

## 验收条件

- [x] `backend/pyproject.toml` 声明与 Uvicorn 0.22.0 兼容的固定 `websockets` 运行依赖。
- [x] 启动测试确认测试/运行镜像可以导入 `websockets`，并拒绝无协议实现的依赖回归。
- [x] 既有 `/api/v1/events/ws` 认证、游标、事件信封和关闭码测试通过。
- [x] 完成 Fast/Final 要求的测试、差异审计和 `git diff --check`。

## Definition of Ready

- [x] TASK-013 已 completed，实时事件契约已冻结。
- [x] 正式日志已复现 `Unsupported upgrade request`、缺少 WebSocket library 和 `/api/v1/events/ws` 404 的组合现象。
- [x] 已确认代码路由存在，缺陷边界仅在运行依赖。
- [x] 变更规格、任务索引和追踪矩阵已同步。

## 实现批次

1. 以启动测试冻结 WebSocket 依赖声明和导入能力。
2. 添加最小固定运行依赖，运行事件集成测试。
3. Fast、完整差异审计和 Final Compose 验证。
4. 更新任务状态与交接，创建独立中文 Git 提交。

## 实现文件

**修改**:

- `backend/pyproject.toml` - WebSocket 运行依赖。
- `backend/tests/start/test_websocket_runtime_dependency.py` - 运行依赖门禁。
- `docs/specs/001-sakuraplayer-v1/changes/2026-08-02--websocket-runtime-dependency.md` - 变更边界。
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-224.md` - 任务状态与证据。
- `docs/specs/001-sakuraplayer-v1/2026-08-01--runtime-fixes--tasks.md` - 运行修复任务索引。
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md` - 总任务索引。
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md` - AC/任务映射。
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md` - 会话恢复状态。

## 测试说明

- 解析项目依赖并导入 `websockets`。
- 运行 `tests/integration/events/test_reconnect_snapshot.py`。
- 运行后端 Ruff、相关 pytest、完整自包含测试与 Compose Final；不降低既有断言。

## Definition of Done

- [x] 运行镜像具备 WebSocket 协议实现，日志组合问题已修复。
- [x] 事件契约和客户端行为未改变，所有要求测试通过。
- [x] 任务状态、追踪矩阵和交接已同步。
- [x] 只暂存 TASK-224 相关文件并创建中文 Git 提交。

## 完成证据

- `websockets==12.0` 已安装进 Python 3.10.16 测试和运行镜像；Uvicorn WebSocket protocol class 可导入。
- Focused：运行依赖与事件 WebSocket 测试 `2 passed`。
- Fast：Ruff format/check 通过；自包含测试 `843 passed, 9 deselected`。
- Final：自包含测试 `843 passed, 9 deselected`；PostgreSQL integration/E2E `127 passed, 16 deselected`；Compose 迁移、五服务健康、认证 canary、重启、ready 降级恢复、秘密扫描和资源清理通过。
