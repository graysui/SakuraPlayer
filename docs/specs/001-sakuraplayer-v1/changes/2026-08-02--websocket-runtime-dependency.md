# Change Specification: WebSocket 运行依赖补齐

**Type**: Delta
**Date**: 2026-08-02
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

正式 API 日志显示 Uvicorn 收到 `/api/v1/events/ws` 升级请求时没有可用的 WebSocket 实现，随后把请求按普通 HTTP 处理并返回 404。代码已经注册该路由，问题来自运行镜像依赖不完整。本变更新增 TASK-224，只补齐固定版本的 `websockets` 运行依赖，不改变实时事件协议或客户端行为。

## ADDED

- REQ-CHG-279：新增 TASK-224，负责 API 运行镜像的 WebSocket 协议实现依赖和启动级验证。

## MODIFIED

- REQ-CHG-280：实现 WebSocket 事件契约的 API 镜像必须安装并能够导入一个受 Uvicorn 0.22.0 支持的 WebSocket 实现；缺失该依赖不能作为可交付运行配置。
- REQ-CHG-281：`GET /api/v1/events/ws` 的路径、Bearer 认证、事件信封、游标和关闭码保持现有 `realtime-events.md` 不变；本变更只修复协议升级层。

## Acceptance Criteria

- [x] API 运行依赖声明固定版本的 `websockets`，并且测试镜像内可以导入。
- [x] 已有认证事件 WebSocket 集成测试继续验证 `/api/v1/events/ws`，不因依赖修复放宽认证或关闭码断言。
- [x] Uvicorn 不再因为缺少 WebSocket 实现而对该路径记录 `Unsupported upgrade request` 并返回 404；完整 Compose 启动后通过健康与事件相关门禁。

## Testing Strategy

- 启动测试解析 `pyproject.toml`，确认固定 `websockets` 声明和运行时模块可导入。
- 运行事件 WebSocket 集成测试，验证路由、认证、事件重放和关闭码不变。
- Fast/Final 按统一实施与验证流程运行；不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

只能通过新的前向变更调整 WebSocket 实现版本或 Uvicorn 兼容策略；不得删除运行依赖、改用无协议支持的基础镜像或修改事件契约来绕过失败。

## Completion Evidence

- `websockets==12.0` 在最终 API/测试镜像安装成功。
- Compose Final 自包含 `843 passed, 9 deselected`，PostgreSQL integration/E2E `127 passed, 16 deselected`，服务健康、迁移、重启、ready 降级恢复和资源清理全部通过。
