---
id: TASK-002
title: "唯一管理员认证与会话"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: implemented
implemented_date: 2026-07-24
dependencies: [TASK-001]
ac-mapping: [AC-001, AC-002, AC-004, AC-010, AC-011, AC-012, AC-133]
imp-requirements: [REQ-001, REQ-003, REQ-025]
cross-boundary: false
external-dependency-risk: false
provides: [admin auth, refresh sessions, auth middleware]
---

# TASK-002: 唯一管理员认证与会话

**功能描述**: 实现受一次性 bootstrap token 保护的首次引导、唯一管理员、Argon2id 密码、短期访问令牌、可撤销刷新会话和退出登录清理信号。

**规格映射**: AC-001、AC-002、AC-004、AC-010 至 AC-012、AC-133

## 验收条件

- [x] 首次部署只有持有正确 bootstrap token 才能创建唯一管理员；先查管理员存在，已初始化直接 409 且不再比较 secret；未初始化先校验 token，正确后才解析 body；缺失/错误、畸形 body、并发重复均被稳定拒绝，保持配置或轮换 secret 都不能创建或替换管理员；对应 AC-001、AC-133。
- [x] 业务 API、WebSocket 和播放签发入口使用有效身份凭据；对应 AC-002。
- [x] 密码仅以适合密码存储的单向算法保存，访问令牌短期、刷新会话可撤销且数据库不保存明文密码；对应 AC-010、AC-011。
- [x] 退出登录撤销 access `sid` 对应本机会话并以 204 指示调用客户端清除本地令牌/字幕缓存，同时递增 session epoch 撤销旧 access/播放能力；其他未撤销客户端可 refresh 恢复；产品不出现年龄确认页面；对应 AC-012、AC-004。

## Definition of Ready

- [x] TASK-001 的数据库和应用组合根可运行。
- [x] Argon2id、JWT 访问/刷新有效期、session epoch 和 bootstrap header 已按技术计划/OpenAPI 冻结。
- [x] 客户端实例 ID 与注销语义已在 OpenAPI 中确认。

## 技术上下文

- `identity` 上下文拥有 `admin_user`、`refresh_session`。
- 密码使用 argon2-cffi 23.1.0；令牌使用 PyJWT 2.10.1。
- JWT 只使用运行配置契约中的独立 token key；bootstrap token 只比较、不持久化，也不参与 JWT 签名。
- access/refresh JWT 只接受 HS256 并以 `typ` 分离；刷新令牌只存 SHA-256，30 天绝对期限内原子轮换，旧 token 重放撤销本机 sid。
- 退出登录撤销当前 sid 并递增 `session_epoch`，使旧 access/播放能力失效；其他未撤销客户端可 refresh 到新 epoch。
- API 依赖注入统一提供 `CurrentAdmin`；路由不自行解析 token。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/identity/domain.py` - 管理员和会话值对象。
- `backend/src/sakuraplayer/identity/service.py` - bootstrap/login/refresh/logout 用例。
- `backend/src/sakuraplayer/identity/api.py` - 认证路由和中间件依赖。
- `backend/tests/unit/identity/test_auth_service.py` - 密码、令牌和撤销单测。
- `backend/tests/integration/identity/test_auth_api.py` - API 认证流程。
- `backend/tests/integration/identity/test_bootstrap_token.py` - 初始化口令、并发和日志脱敏。

## 测试说明

**单元测试**:

- 验证 Argon2id 哈希不可逆、错误密码不登录、访问令牌过期和 session epoch 撤销。
- 验证缺失/错误/正确 bootstrap token、同一管理员第二次 bootstrap、无 access token、过期/重放 refresh 和 token 类型混淆的错误码。

**集成测试**:

- 调用 bootstrap/login/refresh/logout 后访问受保护业务、WebSocket 和签发前置依赖，验证状态码和 token 轮换。
- 验证 logout 后当前 sid 的旧 refresh/access 失效、204 清理语义、其他客户端 refresh 恢复及旧 epoch 播放能力失效。

**边界条件**:

- 并发 bootstrap、token 日志脱敏、重复 refresh、刷新令牌重放、密码边界长度。

## Definition of Done

- [x] 唯一管理员和令牌生命周期持久化完成。
- [x] 受保护路由统一接入，未增加年龄确认页面。
- [x] 单元/集成测试通过，日志不包含密码或令牌。

**依赖**: TASK-001

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-002.md"`
