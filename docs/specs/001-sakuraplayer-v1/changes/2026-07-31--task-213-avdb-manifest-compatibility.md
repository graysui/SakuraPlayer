# Change Specification: TASK-213 AVdb manifest 兼容边界

**Type**: Delta
**Date**: 2026-07-31
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-213 第二次隔离 Final 已通过现行资产名发现、GitHub 重定向、大小与 SHA-256 下载门禁，但官方
现行外层 manifest 在既有加密参数之外新增 `format`、`version`、`payload` 和
`original_filename`。现有严格未知字段拒绝规则因此在 GCM 解密前稳定返回 `avdb_asset_invalid`。
本变更仅为四个公开声明字段增加严格白名单，不改变 PBKDF2 参数、AES-GCM 认证、ZIP/CSV 边界、
摘要校验或导入规则。

## ADDED

- 旧 manifest 继续只要求 `salt`、`nonce`、`tag` 和 `iterations`，并允许既有算法、KDF 与密钥长度
  声明。
- 新声明字段若出现，`format`、`version`、`payload` 和 `original_filename` 必须四项成组出现。
- `format` 必须恰好为 `avdb-resource-library`，`version` 必须是整数 `1`，`payload` 必须恰好为
  `avdb-resource-library.bin`。
- `original_filename` 必须整串匹配冻结的增量或全量资产名白名单；路径、前后缀和额外扩展名继续
  拒绝。

## MODIFIED

- manifest 的允许字段集合增加上述四项固定声明；其他未知字段继续返回 `avdb_asset_invalid`。
- AVdb 数据源与解密契约版本由 1.1.0 升至 1.2.0，不新增错误码。
- TASK-004 继续拥有 AVdb 解密与导入主责；TASK-213 仅修复真实门禁发现的官方 manifest 兼容阻断。

## Acceptance Criteria

- [ ] 旧 manifest fixture 继续成功解密。
- [ ] 官方现行四字段 manifest 成功进入 GCM 认证和 CSV 导入。
- [ ] 四字段缺项、错误固定值、非整数版本、非白名单原始文件名和其他未知字段继续返回
  `avdb_asset_invalid`。
- [ ] 真实主源或备用源最新 30D release 在隔离数据库中完成导入。
- [ ] 默认测试仍不访问真实 GitHub、115、JavDB 写操作或付费 AI。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-005 / AC-018..AC-021 | MODIFIED | HIGH |
| AVdb source contract | MODIFIED | HIGH |
| TASK-213 / traceability matrix | MODIFIED | MEDIUM |
| AVdb manifest validator | MODIFIED | MEDIUM |

## Testing Strategy

- 单元测试覆盖旧 manifest、现行四字段 manifest 和每个拒绝边界。
- 受影响 Fast 运行 AVdb crypto/release/worker 与启动日志测试。
- Final 销毁失败验收卷后，在全新隔离 Compose 中重新导入真实 30D release。

## Rollback Plan

若现行 manifest 仍无法通过摘要、GCM 或 ZIP/CSV 门禁，保留失败证据并回退本变更；不得删除未知字段
拒绝、降低固定字段断言、关闭 GCM/摘要校验或导入未验证资产。

## Task Impact

不新增任务。TASK-213 增加一次阻断兼容修复并映射 AC-018 至 AC-021；TASK-004 的既有主责和完成
状态不变，后续 TASK-214 仍依赖 TASK-213 完整完成。
