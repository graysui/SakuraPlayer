---
id: TASK-219
title: "前后端开发期热更新"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-001, TASK-202]
ac-mapping: [AC-134, AC-135]
imp-requirements: [REQ-025]
cross-boundary: true
external-dependency-risk: false
provides: [backend compose watch, Windows hot reload default server]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-219: 前后端开发期热更新

**功能描述**: 为三个后端常驻进程配置开发专用 Compose Watch，并让 Windows Hot Reload 启动时可通过安全 Dart define 连接本机后端。

**实施边界**: [前后端开发期热更新](../changes/2026-08-01--development-hot-reload.md)

## 验收条件

- [x] `api`、`worker`、`scheduler` 同步 `backend/src` 后重启，依赖与镜像入口变化触发 rebuild；正式 Compose 无 Watch。
- [x] 迁移、secret、端口和卷不自动 Watch，开发卷不因热更新被清除。
- [x] Windows 无保存地址时读取合法 `SAKURAPLAYER_DEFAULT_API_BASE_URL`；保存地址优先，非法默认值仍被统一安全策略拒绝。
- [x] 开发指南与实际命令一致，后端 Watch 和 Windows Hot Reload 均可启动并保持运行。

## Definition of Ready

- [x] TASK-001、TASK-202 已完成，正式 Compose 与 Windows 地址策略已交付。
- [x] Compose Watch 5.1.4、Flutter Windows Hot Reload 和运行配置契约已核对。
- [x] Delta 已冻结开发覆盖、迁移隔离和默认地址优先级。

## 实现批次

1. 开发 Compose 覆盖与合并配置 Focused 测试。
2. Windows 默认地址接线与保存地址优先/安全策略 Focused 测试。
3. 指南同步、分层验证和实际热更新启动。

## Definition of Done

- [x] Focused/Fast、完整差异审计、正式 Compose Final 和 Windows release 验证通过。
- [x] 后端 Watch 与 Windows Hot Reload 实际启动，现有开发卷和用户配置保持。
- [x] 任务索引、运行文档、追踪矩阵和交接同步并创建独立中文 Git 提交。

**依赖**: TASK-001, TASK-202
