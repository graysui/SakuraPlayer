# Change Specification: 前后端开发期热更新

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

实际联调需要在保持现有数据库卷和登录状态的同时快速验证 Windows 与三个后端常驻进程。现有 Windows 已支持 Flutter Hot Reload，但后端源码只在镜像构建时复制，运行配置契约声明的 Windows 默认 API 基址也尚未接线。本变更新增 TASK-219，落地开发专用 Compose Watch 覆盖和安全默认地址，不改变正式 Compose、发布构建或产品验收门禁。

## ADDED

- REQ-CHG-245: 新增 `backend/docker-compose.dev.yml`，只为 `api`、`worker`、`scheduler` 配置 Compose Watch；`backend/src` 变化使用 `sync+restart`，依赖、Dockerfile和 entrypoint 变化使用 `rebuild`。
- REQ-CHG-246: Alembic 迁移、环境配置、secret、端口和卷不进入自动 Watch；Schema 变化仍必须显式构建、迁移并重启常驻进程。
- REQ-CHG-247: Windows 在没有已保存服务端地址时读取 `SAKURAPLAYER_DEFAULT_API_BASE_URL` Dart define。默认值必须经过既有 `ServerAddressPolicy` 和连接测试；已保存地址始终优先，用户显式保存的地址不被构建参数覆盖。
- REQ-CHG-248: 开发指南提供可执行的后端 Watch 与 Windows Hot Reload 启动、停止和迁移流程；热更新只用于开发反馈，不能代替 Focused、Fast、Final、Compose Final 或 Windows release 门禁。

## MODIFIED

- REQ-CHG-249: 新增 TASK-219，Windows 工作流实现任务由 14 个增至 15 个，总任务数由 61 个增至 62 个；TASK-214 增加 TASK-219 依赖，TASK-217 的业务边界和优先级不变。

## Acceptance Criteria

- [x] Compose 合并配置只给三个后端常驻服务加入正确的 Watch 路径和动作，正式 Compose 文件保持无开发 Watch。
- [x] Windows 无保存地址时可用合法 Dart define 连接；保存地址优先，非法 define 不绕过地址策略。
- [x] 开发指南命令经当前 Docker Compose 与 Flutter Windows 工具链验证，应用以热更新方式启动。
- [x] 热更新验证不访问真实 115、JavDB 写操作或付费 AI，也不清除现有开发卷。

## Testing Strategy

- 后端 Focused 使用 `docker compose config --format json` 验证合并后的三服务 Watch 配置、路径和正式 Compose 隔离。
- Windows Focused 覆盖合法默认值、保存地址优先和非法默认值；Fast 运行完整 analyze/test。
- Final 按统一实施流程验证正式 Compose 与 Windows release 不受开发覆盖影响，再启动开发 Watch 和 Flutter Hot Reload 供人工体验。

## Rollback Plan

可删除开发覆盖文件并恢复手工地址配置；不得通过回退正式 Compose 安全默认值、放宽地址策略或自动执行迁移实现回滚。
