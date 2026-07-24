---
id: TASK-002
title: "唯一管理员认证与会话"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
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

- [ ] 首次部署只有持有正确 bootstrap token 才能创建唯一管理员；缺失/错误、并发重复和管理员已存在均被拒绝；对应 AC-001、AC-133。
- [ ] 业务 API、WebSocket 和播放签发入口使用有效身份凭据；对应 AC-002。
- [ ] 密码仅以适合密码存储的单向算法保存，访问令牌短期、刷新会话可撤销且数据库不保存明文密码；对应 AC-010、AC-011。
- [ ] 退出登录撤销本机会话并发出本地令牌/字幕缓存清理信号；产品不出现年龄确认页面；对应 AC-012、AC-004。

## Definition of Ready

- [ ] TASK-001 的数据库和应用组合根可运行。
- [ ] Argon2id、JWT 访问/刷新有效期、session epoch 和 bootstrap header 已按技术计划/OpenAPI 冻结。
- [ ] 客户端实例 ID 与注销语义已在 OpenAPI 中确认。

## 技术上下文

- `identity` 上下文拥有 `admin_user`、`refresh_session`。
- 密码使用 argon2-cffi 23.1.0；令牌使用 PyJWT 2.10.1。
- JWT 只使用运行配置契约中的独立 token key；bootstrap token 只比较、不持久化，也不参与 JWT 签名。
- 刷新令牌只存哈希；退出登录递增 `session_epoch`，使播放能力失效。
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
- 验证缺失/错误/正确 bootstrap token、同一管理员第二次 bootstrap、无 access token 和过期 refresh 的错误码。

**集成测试**:

- 调用 bootstrap/login/refresh/logout 后访问受保护业务、WebSocket 和签发前置依赖，验证状态码和 token 轮换。
- 验证 logout 后旧 refresh、旧 access 和本机字幕清理事件均失效。

**边界条件**:

- 并发 bootstrap、token 日志脱敏、重复 refresh、刷新令牌重放、密码边界长度。

## Definition of Done

- [ ] 唯一管理员和令牌生命周期持久化完成。
- [ ] 受保护路由统一接入，未增加年龄确认页面。
- [ ] 单元/集成测试通过，日志不包含密码或令牌。

**依赖**: TASK-001

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-002.md"`
