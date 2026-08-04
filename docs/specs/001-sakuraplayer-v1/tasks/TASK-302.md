---
id: TASK-302
title: "Asset Store 认证 HTTP WebSocket 与快照"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-301, TASK-013]
ac-mapping: [AC-002, AC-011, AC-012, AC-115, AC-116, AC-117, AC-133, AC-135]
imp-requirements: [REQ-001, REQ-003, REQ-021, REQ-025]
cross-boundary: false
external-dependency-risk: false
provides: [HarmonyOS auth store, typed HTTP client, WebSocket snapshot recovery]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-302: Asset Store 认证 HTTP WebSocket 与快照

**功能描述**: 用 API 24 官方能力实现后端基址配置/测试、安全令牌、严格 ArkTS DTO、HTTP refresh、WebSocket 去重和 REST snapshot 恢复；不要求 API 24 物理真机连接。

**规格映射**: AC-002、AC-011、AC-012、AC-115 至 AC-117、AC-133、AC-135

## 验收条件

- [ ] 所有业务/签发/WebSocket 请求需要有效认证，401 只执行一次 refresh；对应 AC-002、AC-011。
- [ ] 刷新令牌存 Asset Store Kit，明文密码不落盘，logout 删除令牌和字幕缓存；对应 AC-011、AC-012。
- [ ] 事件按 event_id/stream_version 合并，断线/跳号拉 REST snapshot；对应 AC-115、AC-116。
- [ ] 进后台时已在进程内的完成事件可发系统通知，完全退出不常驻，下次启动补拉；对应 AC-117。
- [ ] 登录前配置并测试后端基址；严格校验 URL/私网 HTTP，更换地址删除 Asset Store 旧令牌、字幕和快照；对应 AC-135。
- [ ] 未初始化服务端的管理员创建页临时接收 bootstrap token，经 header 发送后立即清空且不进 Preferences/Asset Store；对应 AC-133。

## Definition of Ready

- [ ] TASK-301 API 24 工程可构建，SDK 签名核验和 AC-131 fixture 基线已通过。
- [ ] 不使用 `any/unknown` 逃避 OpenAPI DTO 校验。
- [ ] 所有 `on/off` listener 使用命名回调并可注销。

## 技术上下文

- 使用 `http.createHttp()` 后 finally destroy；WebSocket close code 按 realtime 契约。
- ArkTS V2 `@ObservedV2/@Trace` 或 StateStore 管理共享会话/快照。
- 不使用后台常驻下载服务；115 任务在后端继续。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/core/api/ApiClient.ets` - typed HTTP/error/refresh。
- `harmony/entry/src/main/ets/core/api/ServerProfile.ets` - URL 规范化、Preferences 和连接测试。
- `harmony/entry/src/main/ets/features/auth/AuthPage.ets` - 后端地址、bootstrap 与登录。
- `harmony/entry/src/main/ets/features/auth/AuthStore.ets` - 临时初始化口令和会话状态。
- `harmony/entry/src/main/ets/core/auth/SecureSessionStore.ets` - Asset Store token。
- `harmony/entry/src/main/ets/core/events/EventClient.ets` - WebSocket/游标/重连。
- `harmony/entry/src/main/ets/core/events/SnapshotStore.ets` - StateStore/V2 snapshot。
- `harmony/entry/src/ohosTest/ets/test/ApiClient.test.ets` - refresh/error tests。
- `harmony/entry/src/ohosTest/ets/test/EventClient.test.ets` - 去重/跳号/生命周期。

## 测试说明

- access/refresh/logout、令牌不进入 preferences/HiLog、logout 清字幕目录。
- 后端地址 URL 边界、TLS 失败、私网 HTTP 确认和换地址清理。
- bootstrap token 缺失/错误/成功/已完成，Preferences/Asset Store/HiLog 无 token。
- 事件重复/跳号/4409/未知类型、resource 类型化字段浅合并、本地缺失 snapshot、未读通知幂等标记已读，以及前后台 listener 注册/注销和重启恢复。
- http/webSocket 资源都在页面/Ability 生命周期正确 destroy/close。

## Definition of Done

- [ ] 认证、Asset Store、HTTP、WebSocket 和 snapshot 完成。
- [ ] ArkTS strict checker 无动态类型逃逸。
- [ ] 无常驻后台服务或秘密日志。

**依赖**: TASK-301, TASK-013

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-302.md"`
