---
id: TASK-302
title: "Asset Store 认证 HTTP WebSocket 与快照"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-301, TASK-312, TASK-013]
ac-mapping: [AC-002, AC-011, AC-012, AC-115, AC-116, AC-117]
imp-requirements: [REQ-001, REQ-003, REQ-021]
cross-boundary: false
external-dependency-risk: false
provides: [HarmonyOS auth store, typed HTTP client, WebSocket snapshot recovery]
---

# TASK-302: Asset Store 认证 HTTP WebSocket 与快照

**功能描述**: 用 API 24 官方 Asset Store Kit/Network Kit 实现安全令牌、严格 ArkTS DTO、HTTP refresh、WebSocket 去重和 REST snapshot 恢复。

**规格映射**: AC-002、AC-011、AC-012、AC-115 至 AC-117

## 验收条件

- [ ] 所有业务/签发/WebSocket 请求需要有效认证，401 只执行一次 refresh；对应 AC-002、AC-011。
- [ ] 刷新令牌存 Asset Store Kit，明文密码不落盘，logout 删除令牌和字幕缓存；对应 AC-011、AC-012。
- [ ] 事件按 event_id/stream_version 合并，断线/跳号拉 REST snapshot；对应 AC-115、AC-116。
- [ ] 进后台时已在进程内的完成事件可发系统通知，完全退出不常驻，下次启动补拉；对应 AC-117。

## Definition of Ready

- [ ] TASK-301 API 24 工程可构建，TASK-312 的 AC-131 真机前置门禁已通过。
- [ ] 不使用 `any/unknown` 逃避 OpenAPI DTO 校验。
- [ ] 所有 `on/off` listener 使用命名回调并可注销。

## 技术上下文

- 使用 `http.createHttp()` 后 finally destroy；WebSocket close code 按 realtime 契约。
- ArkTS V2 `@ObservedV2/@Trace` 或 StateStore 管理共享会话/快照。
- 不使用后台常驻下载服务；115 任务在后端继续。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/core/api/ApiClient.ets` - typed HTTP/error/refresh。
- `harmony/entry/src/main/ets/core/auth/SecureSessionStore.ets` - Asset Store token。
- `harmony/entry/src/main/ets/core/events/EventClient.ets` - WebSocket/游标/重连。
- `harmony/entry/src/main/ets/core/events/SnapshotStore.ets` - StateStore/V2 snapshot。
- `harmony/entry/src/ohosTest/ets/test/ApiClient.test.ets` - refresh/error tests。
- `harmony/entry/src/ohosTest/ets/test/EventClient.test.ets` - 去重/跳号/生命周期。

## 测试说明

- access/refresh/logout、令牌不进入 preferences/HiLog、logout 清字幕目录。
- 事件重复/跳号/4409/未知类型、前后台 listener 注册/注销和重启 snapshot。
- http/webSocket 资源都在页面/Ability 生命周期正确 destroy/close。

## Definition of Done

- [ ] 认证、Asset Store、HTTP、WebSocket 和 snapshot 完成。
- [ ] ArkTS strict checker 无动态类型逃逸。
- [ ] 无常驻后台服务或秘密日志。

**依赖**: TASK-301, TASK-312, TASK-013

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-302.md"`
