---
id: TASK-202
title: "API、令牌、事件与快照基础"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
implemented_date: 2026-07-29
completed_date: 2026-07-29
dependencies: [TASK-201, TASK-013]
ac-mapping: [AC-002, AC-011, AC-012, AC-115, AC-116, AC-117, AC-133, AC-135]
imp-requirements: [REQ-001, REQ-003, REQ-021, REQ-025]
cross-boundary: false
external-dependency-risk: false
provides: [Dio API client, secure token store, WebSocket client, snapshot recovery]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-202: API、令牌、事件与快照基础

**功能描述**: 实现后端基址配置/测试、OpenAPI DTO、Dio 认证/refresh、安全存储、WebSocket 去重/版本检测、REST snapshot 恢复和前后台生命周期。

**实施边界**: [TASK-202 客户端基础确定性边界](../changes/2026-07-29--task-202-client-foundation-boundaries.md)

**规格映射**: AC-002、AC-011、AC-012、AC-115 至 AC-117、AC-133、AC-135

## 验收条件

- [x] 所有业务/签发/事件调用附带有效认证；并发 401 共用 single-flight refresh，等待请求各自最多重放一次；对应 AC-002、AC-011。
- [x] 不保存明文密码；logout 删除 token 和本地字幕缓存；对应 AC-011、AC-012。
- [x] 事件按 event_id 去重、stream_version 跳号后拉 REST snapshot；对应 AC-115、AC-116。
- [x] 提供可注销生命周期与通知投递端口；后台/重启补拉未读并仅在真实展示后幂等标记已读，完全退出不常驻；Windows 平台通知适配器归 TASK-209；对应 AC-117。
- [x] 登录前配置并测试后端基址；拒绝 userinfo/query/fragment 和公网明文 HTTP，更换地址先注销并清除旧状态；对应 AC-135。
- [x] 未初始化服务端的管理员创建表单临时接收 bootstrap token 并通过 header 发送，提交后立即清空且不持久化；对应 AC-133。
- [x] 首次启动生成 UUID v4 `client_instance_id` 并安全持久化；logout、refresh 失败和更换地址不改变它；对应 AC-011。

## Definition of Ready

- [x] TASK-201 组合根可运行，OpenAPI/realtime/error code 契约冻结。
- [x] 架构已冻结 flutter_secure_storage 9.2.0 和 Dio 5.7.0；TASK-202 第一批次加入 Windows 直接依赖和锁文件。
- [x] `client_instance_id` 的生成、持久化和保留语义已由实施边界冻结，能力由 TASK-202 第一批次交付。

## 技术上下文

- API DTO 不使用动态 map 逃避校验；未知事件触发一次 snapshot 而非崩溃。
- refresh token 只进 secure storage；access token 不写普通偏好。
- 生命周期 listener 必须可注销，测试不依赖真实系统通知。
- 手写严格 DTO，不引入 json_serializable/freezed/build_runner；JSON map 不越过网络解析边界。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/core/api/api_client.dart` - Dio JSON/bytes 和错误映射。
- `windows/lib/core/api/api_models.dart` - 手写严格 OpenAPI/事件 DTO。
- `windows/lib/core/api/server_profile.dart` - 后端基址规范化、持久化和连接测试。
- `windows/lib/features/auth/presentation/server_setup_page.dart` - 地址、连接测试与初始化/登录入口。
- `windows/lib/features/auth/presentation/auth_controller.dart` - bootstrap token 生命周期和登录状态。
- `windows/lib/core/auth/session_store.dart` - token rotation/logout。
- `windows/lib/core/storage/secure_store.dart` - refresh/client ID。
- `windows/lib/core/events/event_client.dart` - WebSocket/游标/重连。
- `windows/lib/core/events/snapshot_controller.dart` - REST 恢复。
- `windows/lib/core/events/app_lifecycle.dart` - 可注销生命周期和通知投递端口。
- `windows/test/core/api_client_test.dart` - 401/refresh/error code。
- `windows/test/core/event_client_test.dart` - 去重/跳号/后台。

## 测试说明

**单元测试**:

- access 过期只 refresh 一次、并发 401 共用一次 rotation、logout 后旧 token 不重放、错误 code 映射。
- URL scheme/私网判断/TLS 错误/远程 HTTP 风险确认，以及换地址后的会话清理。
- bootstrap token 缺失/错误/成功/已完成，Widget/controller 树和日志中无残留 token。
- event 重复/跳号/未知版本/4409，快照后的未知聚合版本基线，resource 类型化字段浅合并，本地缺失时以 snapshot 替换状态；未读通知仅在展示成功后幂等标记已读。

**集成测试**:

- Fake backend 登录 -> 业务请求 -> access 过期 -> rotate -> logout，确认字幕目录删除。
- 前后台/完全重启后补拉 ready/failed 任务和未读通知，不常驻连接。

## Definition of Done

- [x] 认证、secure storage、API、事件和 snapshot 完成。
- [x] 退出清理和重连恢复有测试证据。
- [x] 日志无 token/签名 URL。

## Implementation Summary

- 加入 Dio 5.7.0 与 flutter_secure_storage 9.2.0，建立严格 DTO、类型化错误、TLS 失败映射、
  UUID v4 客户端实例安全持久化，以及并发/迟到 401 共用 refresh rotation 的认证客户端。
- 实现 HTTPS/私网 HTTP 地址策略、连接测试、初始化管理员与登录 UI；bootstrap token 仅进入
  header 和临时输入控制器，更换服务端会尽力注销旧会话并清除 token、字幕与运行时状态。
- 实现认证 WebSocket、event_id/sequence/stream_version 合并、未知聚合版本快照基线、4409
  恢复、首次连接与断线重连，以及可注销生命周期、通知投递端口和展示成功后的幂等已读。
- `dart format`、`flutter analyze`、32 项 `flutter test` 和 Windows debug build 通过；构建环境
  已为实际使用的 Visual Studio BuildTools 2022 补齐 ATL，成功生成 Windows exe 与安全存储插件。

**完成日期**: 2026-07-29

**依赖**: TASK-201, TASK-013

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-202.md"`
