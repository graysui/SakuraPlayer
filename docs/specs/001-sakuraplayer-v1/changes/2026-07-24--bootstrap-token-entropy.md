# Change Specification: Bootstrap Token 熵与比较规范

**Type**: Delta
**Date**: 2026-07-24
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

运行配置要求 bootstrap token 至少包含 32 个随机字节，但既有配置校验和 OpenAPI 只要求 32 个 URL-safe 字符，可能只提供约 24 字节材料；同时直接比较变长 header 与 secret 不能形成固定长度比较。本变更冻结编码、熵和常量时间比较方式。

## Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### Bootstrap Token 规范编码

**Requirements**:

- REQ-CHG-024: bootstrap token 必须由至少 32 个随机字节编码为 43..512 字符的无 padding Base64URL 文本，配置加载时必须解码并验证材料长度、上限与规范编码。

**Acceptance Criteria**:

- [x] 32 随机字节编码后的最短 token 为 43 字符；32 个普通 Base64URL 字符或 31 字节材料被拒绝。
- [x] secret 文件和环境变量使用相同校验，不在错误中回显 token。

## MODIFIED

### Bootstrap Token 常量时间比较

**Previous Behavior**: 直接对长度可控的 header 字节与配置 secret 文本执行 `compare_digest`。

**New Behavior**: 服务启动时可把配置 secret 归一为带用途域分隔的 SHA-256 并仅保留摘要；请求时对输入计算同域摘要，再对两个固定 32 字节摘要执行 `compare_digest`。管理员存在的 bootstrap 请求不得计算请求摘要或调用比较器。

**Requirements**:

- REQ-CHG-025: 缺失、短、长、非 ASCII 或错误 bootstrap header 必须走固定长度摘要比较并统一返回 `bootstrap_token_invalid`。

**Acceptance Criteria**:

- [x] 所有错误 header 返回相同 code 且不回显输入；正确 token 仍可完成唯一 bootstrap。
- [x] 管理员存在后的测试证明比较器未被调用。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 运行配置与 OpenAPI | MODIFIED | MEDIUM |
| TASK-002 bootstrap 服务与测试 | MODIFIED | MEDIUM |

## Testing Strategy

- 配置测试覆盖 31/32 字节边界、非规范 Base64URL 和秘密不回显。
- 服务测试覆盖缺失、短、长、Unicode、错误、正确和初始化后不比较。

## Rollback Plan

实现尚未发布。若回退必须同时回退配置、OpenAPI 和比较逻辑；不得只放宽其中一个边界。
