# Change Specification: Actor Mapping blacklist 结构兼容

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-217 正式首次快照发现固定 Actor Mapping 上游在 `actor` 分组之后新增空的
`actor-blacklist` 分组。原 REQ-CHG-064 只允许 `actor-mapping/actor/a`，因此安全解析器把
当前真实文件稳定拒绝为 `provider_snapshot_invalid`。本变更只兼容该已知分组，保持条目
白名单、XXE 防护、大小上限和演员身份边界不变。

## ADDED

- REQ-CHG-261: Actor Mapping 根节点只允许无属性的 `actor` 与 `actor-blacklist` 分组；
  `actor` 必须至少包含一个 `a` 条目，`actor-blacklist` 可以为空。未知分组、分组属性、
  空 `actor` 或没有可用 `actor` 条目的文件继续返回 `provider_snapshot_invalid`。
- REQ-CHG-262: 非空 `actor-blacklist` 中每个 `a` 必须通过与 `actor` 相同的标签、子节点、
  必需字段、可选字段和长度校验，但 blacklist 条目不得进入映射结果、演员匹配或数据库写入。
  DTD、实体和外部网络拒绝边界不变。

## MODIFIED

- REQ-CHG-263: REQ-CHG-064 的允许结构由 `actor-mapping/actor/a` 精确扩展为本变更的
  `actor-mapping/(actor|actor-blacklist)/a`；其他下载、解析、身份和持久化边界均不变。
  TASK-217 完成门禁增加当前真实 XML 的无写解析证据和正式 current snapshot 证据。

## Acceptance Criteria

- [x] 当前真实 Actor Mapping 文件可解析，26,552 条 `actor` 记录进入映射结果，空 blacklist 不报错。
- [x] blacklist 条目通过严格校验但不进入结果；未知字段、未知分组、仅 blacklist 和 XXE 继续拒绝。
- [x] 正式 worker 建立 Actor Mapping current snapshot，历史失败事实保留且没有自动重试。

## Testing Strategy

- 默认测试只使用内联脱敏 XML，覆盖空/非空 blacklist、畸形条目、仅 blacklist 与既有 XXE fixture。
- 真实验证只下载固定无 query URL，在内存中报告正文大小和解析条目数，不保存或输出完整正文。
- Fast/Final 继续按统一实施流程运行；默认门禁不访问真实 GitHub Raw。

## Impact

- Affected: TASK-217、Actor Mapping parser、元数据提供方契约和追踪说明。
- Breaking: NO。只恢复固定上游当前结构，未放宽未知 XML 或演员身份边界。
- Task count: 不新增任务。

## Rollback Plan

若上游移除 `actor-blacklist`，兼容解析仍接受原 `actor` 单分组文件。后续如出现新的分组、属性
或条目结构，必须新增 Delta 与安全回归测试，不得继续扩大白名单。
