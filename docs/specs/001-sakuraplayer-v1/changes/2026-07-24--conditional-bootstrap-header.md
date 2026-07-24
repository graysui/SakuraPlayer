# Change Specification: Bootstrap Header 条件校验

**Type**: Delta
**Date**: 2026-07-24
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

AC-133 与已接受的 bootstrap secret 生命周期要求管理员存在后只依据数据库事实永久拒绝初始化，不得再次比较 secret。现有 OpenAPI 却把 `X-Bootstrap-Token` 定义为协议层始终必填，导致已初始化请求在进入业务逻辑前因缺少 header 返回 422，无法满足稳定的 `bootstrap_already_completed` 语义。本变更把 header 冻结为条件必填。

## Change Summary

| Classification | Count |
|---|---:|
| ADDED | 0 |
| MODIFIED | 1 |
| REMOVED | 0 |

## MODIFIED

### Bootstrap Header 校验时机

**Previous Behavior**: OpenAPI 将 `X-Bootstrap-Token` 标记为始终必填；缺少 header 的请求可在检查管理员状态前被请求校验拒绝。

**New Behavior**:

- `X-Bootstrap-Token` 在 OpenAPI 传输层为可选，在服务端确认尚无管理员时才是业务必填。
- 尚无管理员时，缺失或错误 header 统一返回 401 `bootstrap_token_invalid`。
- 管理员已存在时，无论 header 缺失、错误、正确或 secret 已轮换，都只返回 409 `bootstrap_already_completed`，且不得读取或比较 bootstrap secret。

**Requirements**:

- REQ-CHG-012: 当管理员已存在时，系统必须先依据数据库事实关闭 bootstrap，再处理任何初始化口令值。
- REQ-CHG-013: 当管理员不存在时，系统必须以常量时间校验初始化口令，并将缺失和错误统一映射为 `bootstrap_token_invalid`。

**Acceptance Criteria**:

- [x] 未初始化时缺失或错误 `X-Bootstrap-Token` 均返回 401 `bootstrap_token_invalid`，且不创建管理员。
- [x] 已初始化时缺失、错误或正确 `X-Bootstrap-Token` 均返回 409 `bootstrap_already_completed`，且测试证明不会调用 secret 比较。
- [x] OpenAPI 不再让框架级 required header 校验抢先于管理员存在检查。

**Impact**:

- Affected: AC-133、认证 OpenAPI、错误映射、TASK-002、Windows/HarmonyOS bootstrap 客户端。
- Breaking: NO；未初始化客户端仍必须发送 header，已初始化客户端获得更稳定且更少泄露的响应。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| `contracts/rest-api.openapi.yaml` | MODIFIED | MEDIUM |
| TASK-002 bootstrap API 与测试 | MODIFIED | MEDIUM |
| TASK-202/TASK-302 客户端初始化流程 | MODIFIED | LOW |

## Testing Strategy

- API 测试覆盖未初始化时 header 缺失、错误和正确。
- API 测试覆盖已初始化时 header 缺失、错误、正确和运行 secret 轮换。
- 并发集成测试证明只创建一个管理员，失败请求不替换管理员。
- 日志与数据库扫描证明 bootstrap secret 未被持久化或输出。

## Rollback Plan

若回退本变更，必须同时回退 bootstrap 生命周期的“管理员存在后不再比较 secret”规则；不能只把 OpenAPI 恢复为始终必填，否则会重新产生冻结契约冲突。
