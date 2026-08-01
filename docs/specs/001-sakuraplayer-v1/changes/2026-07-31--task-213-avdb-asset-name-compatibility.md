# Change Specification: TASK-213 AVdb 资产名兼容边界

**Type**: Delta
**Date**: 2026-07-31
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-213 真实门禁准备时，主源和备用源的最新 GitHub Release 均返回
`30D_YYYY-MM-DD-HH-MM-SS.zip`，全量资产也使用相同带连字符时间戳；现有 TASK-004 实现仅接受
8 至 14 位紧凑数字时间戳，导致两个权威源都在下载前稳定失败为 `avdb_asset_invalid`，隔离验收库无法取得
真实来源。本变更只扩展冻结资产名的时间戳表示，不改变仓库、资产前缀、计数、扩展名、摘要、解密或
导入规则。

## ADDED

- `timestamp` 允许既有 8 至 14 位紧凑数字格式，以及官方现行格式
  `YYYY-MM-DD-HH-MM-SS`。
- 增量资产完整格式为 `30D_{timestamp}.zip`。
- 全量资产完整格式为 `All_sehuatang_{count}_{timestamp}.zip` 或
  `All_X1080X_{count}_{timestamp}.zip`。
- 两种格式都必须整串匹配；前后缀、路径段、其他分隔符、缺少秒字段和额外扩展名继续拒绝。

## MODIFIED

- TASK-004 继续拥有 AVdb 发现、摘要、解密和导入；TASK-213 仅修复并验证阻断真实门禁的资产名兼容。
- `avdb_asset_invalid` 继续覆盖不在上述白名单内的资产名，不新增错误码。

## Acceptance Criteria

- [ ] 增量与两种全量资产均接受紧凑时间戳和带连字符时间戳。
- [ ] 前缀污染、缺秒连字符格式、路径名和双扩展名继续返回 `avdb_asset_invalid`。
- [ ] 真实主源或备用源最新增量 release 可进入下载、摘要和解密阶段。
- [ ] 默认测试仍不访问真实 GitHub、115、JavDB 写操作或付费 AI。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-005 / AC-018..AC-021 | MODIFIED | HIGH |
| AVdb source contract | MODIFIED | HIGH |
| TASK-213 / traceability matrix | MODIFIED | MEDIUM |
| AVdb asset-name validator | MODIFIED | LOW |

## Testing Strategy

- 单元测试覆盖增量、sehuatang 全量和 X1080X 全量的两种允许时间戳。
- 拒绝样本覆盖前缀污染、缺少秒、路径、双扩展名和非白名单分隔符。
- 受影响 Fast 运行 AVdb crypto/release/worker 测试；Final 在隔离 Compose 中重新导入真实 30D release。

## Rollback Plan

若官方 release 无法通过后续摘要或解密门禁，保留失败证据并回退本变更的规格、正则和测试；不得通过
关闭摘要、放宽 URL/ZIP/manifest 校验或导入未验证资产来绕过阻断。

## Task Impact

不新增任务。TASK-213 增加一次阻断兼容修复并映射 AC-018 至 AC-021；TASK-004 的既有主责和完成
状态不变，后续 TASK-214 仍依赖 TASK-213 完整完成。
