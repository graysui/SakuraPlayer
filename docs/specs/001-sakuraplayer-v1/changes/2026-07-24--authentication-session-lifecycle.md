# Change Specification: 认证会话生命周期补强

**Type**: Delta
**Date**: 2026-07-24
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-002 实施前审计发现访问令牌 claim、刷新轮换/重放、logout 与 `session_epoch`、客户端实例和本地清理信号尚未形成可测试的单一语义。本变更在不改变 AC-001、AC-002、AC-010 至 AC-012 产品目标的前提下冻结认证会话生命周期。

## Change Summary

| Classification | Count |
|---|---:|
| ADDED | 4 |
| MODIFIED | 3 |
| REMOVED | 0 |

## ADDED

### JWT 类型与 Claims

**Requirements**:

- REQ-CHG-014: 服务端必须仅接受 `HS256`，并按 `typ` 严格区分 access 与 refresh JWT，拒绝 `none`、其他算法、类型互换、坏签名和缺失 claim。
- REQ-CHG-015: access JWT 必须包含 `typ/access`、`sub/admin_id`、`sid/refresh_session_id`、`epoch`、`iat`、`exp`、`jti`；refresh JWT 必须包含 `typ/refresh`、`sub`、`sid`、`iat`、`exp`、`jti`。

**Acceptance Criteria**:

- [x] access 固定 15 分钟，refresh 会话固定为登录时起 30 天绝对有效期。
- [x] 所有时间和 UUID claim 做类型与边界校验，未来 `iat`、过期 `exp` 和 access/refresh 混用均被拒绝。

### 刷新轮换与重放

**Requirements**:

- REQ-CHG-016: 数据库只保存当前 refresh JWT 的 SHA-256；刷新必须锁定 `sid` 对应行并在同一事务中校验 hash、轮换 token hash 和更新时间。
- REQ-CHG-017: 已签名且 `sid` 存在但 hash 不再匹配的旧 refresh JWT 视为重放，必须撤销该客户端 refresh session；并发刷新最多一个请求返回成功。

**Acceptance Criteria**:

- [x] 成功刷新返回新的 access/refresh，旧 refresh 不可再次使用，30 天绝对到期时间不延长。
- [x] 过期、坏签名或未知 sid 返回 `refresh_token_invalid`；已轮换 token 重放返回 `refresh_token_reused` 并撤销该 sid。

### 客户端实例会话

**Requirements**:

- REQ-CHG-018: `client_instance_id` 是客户端安装配置生成并持久化的稳定 UUID；同一管理员与客户端实例最多一个未撤销 refresh session，新登录原子撤销旧会话后创建新会话。

**Acceptance Criteria**:

- [x] 同一 client instance 重登后旧 access/refresh 立即失效，不同 client instance 可并存。
- [x] 同一 client instance 并发登录不得产生 500 或多条活动会话；请求按事务串行，最后提交的登录生效，较早响应的 token 可被后一次登录立即撤销。

### 认证缓存控制

**Requirements**:

- REQ-CHG-019: bootstrap-status、bootstrap、login、refresh 和 logout 响应必须包含 `Cache-Control: no-store`，认证错误不得回显密码、bootstrap token 或任何 JWT。

**Acceptance Criteria**:

- [x] auth 成功与错误响应均不可缓存，日志、响应和验证错误不包含输入秘密。

## MODIFIED

### Logout 与 Session Epoch

**Previous Behavior**: TASK-002 同时要求“本机会话清理”和递增管理员级 `session_epoch`，但未定义其他客户端如何恢复。

**New Behavior**:

- logout 从已签名 access JWT 的 `sid` 定位并撤销当前 refresh session，返回 204；该 204 是调用客户端删除本机 access、refresh 和字幕缓存的协议成功信号，不新增 TASK-110 所属的资源级字幕事件。
- logout 同一事务递增管理员 `session_epoch`，立即撤销全部旧 access JWT 和播放能力。
- 其他未撤销 refresh session 仍可刷新并取得当前 epoch 的新 access；其旧 access 因 epoch 落后返回 `authentication_required`。已撤销 sid 的旧 access 返回 `session_revoked`。

**Requirements**:

- REQ-CHG-020: logout 必须撤销当前 sid、递增 epoch 并以 204 指示调用客户端清理本地认证与字幕状态。

**Acceptance Criteria**:

- [x] 当前客户端旧 access/refresh 均失效；其他客户端旧 access 需要刷新但其 refresh 仍有效；旧播放能力全部失效。

### Bootstrap 请求体校验时机

**Previous Behavior**: 即使 header 改为条件必填，OpenAPI 仍可能在管理员存在检查前因缺少请求体返回 422。

**New Behavior**: bootstrap request body 与 header 均在传输层可选。服务先检查管理员是否存在，已初始化直接 409；未初始化先常量时间校验 header，缺失或错误统一返回 401；只有 token 正确后才解析和校验 body，空或畸形 body 返回 422。

**Requirements**:

- REQ-CHG-021: bootstrap 的管理员存在检查必须先于请求体字段和 secret 校验。
- REQ-CHG-023: 未初始化时 bootstrap token 校验必须先于请求体解析，组合错误不得绕过初始化口令门禁。

**Acceptance Criteria**:

- [x] 已初始化时空请求也返回 `bootstrap_already_completed`；未初始化时空 body 返回安全的 `validation_failed`。
- [x] 未初始化且 header/body 同时错误时返回 `bootstrap_token_invalid`；正确 header 加空或畸形 body 才返回 `validation_failed`。

### 认证错误码

**Previous Behavior**: `authentication_required` 同时可能表达错误密码、refresh 失效和 access 需要刷新，客户端动作会形成错误刷新循环。

**New Behavior**:

- `invalid_credentials`: 登录用户名或密码错误，回登录表单，不自动 refresh。
- `refresh_token_invalid`: refresh 坏签名、过期、未知或已撤销，清理本机会话并回登录页。
- `refresh_token_reused`: 已轮换 refresh 被重放，撤销该客户端会话并清理本机状态。
- `authentication_required`: access 缺失/无效/过期或 epoch 落后，可尝试一次 refresh。
- `session_revoked`: access 的 sid 已撤销，直接清理本机状态。

**Requirements**:

- REQ-CHG-022: 登录、access、refresh 和已撤销会话必须使用不会引发客户端刷新循环的稳定错误码。

**Acceptance Criteria**:

- [x] 每个错误分支返回冻结 code，message/details 不包含秘密。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 认证 OpenAPI 与错误码 | ADDED/MODIFIED | HIGH |
| `admin_user` / `refresh_session` | MODIFIED | HIGH |
| TASK-002 服务、API、迁移与测试 | MODIFIED | HIGH |
| Windows/HarmonyOS 认证客户端任务 | MODIFIED | MEDIUM |
| 播放 session epoch 校验 | MODIFIED | MEDIUM |

## Testing Strategy

- Claims/算法/类型/时间边界与 token 混淆单元测试。
- PostgreSQL 并发 bootstrap、并发 refresh、重放撤销和 client instance 唯一会话测试。
- 两客户端 logout/refresh/session epoch 集成测试。
- HTTP、WebSocket 认证依赖与 auth no-store/秘密脱敏测试。

## Rollback Plan

实现尚未发布。若回退，必须同时回退 OpenAPI、错误码、数据模型、TASK-002 和客户端任务语义，不得保留一半的 refresh 或 epoch 行为。
