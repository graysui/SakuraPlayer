# Change Specification: Bootstrap Secret 生命周期澄清

**Type**: Delta
**Date**: 2026-07-24
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

实施 TASK-001 时发现运行配置契约同时要求生产环境缺少任一启动级 secret 时拒绝启动，又允许管理员创建后移除 bootstrap secret。为避免各进程采用不同解释，本变更冻结 v1 的单一行为：bootstrap secret 始终是后端启动依赖，但唯一管理员创建后永久失去初始化权限。

## MODIFIED

### Bootstrap Secret 生命周期

**Previous Behavior**: bootstrap secret 在管理员创建后的配置要求不一致。

**New Behavior**:

- `SAKURAPLAYER_BOOTSTRAP_TOKEN_FILE` 或其环境变量回退在 v1 中始终是生产启动依赖。
- 管理员创建成功后，所有后续 bootstrap 请求只依据数据库中的管理员存在事实返回 `bootstrap_already_completed`，不得再次比较或使用该 secret 创建、替换管理员。
- 该 secret 仍不得入库、入日志、进入事件或 API 响应；运维可轮换其值，但 v1 不支持从运行配置中移除。

**Requirements**:

- REQ-CHG-011: 各后端进程必须对 bootstrap secret 采用一致的启动校验，且管理员存在后该 secret 不再具有产品权限。

**Acceptance Criteria**:

- [ ] 生产模式缺少 bootstrap secret 时 API、worker 和 scheduler 均以 `startup_configuration_invalid` 拒绝启动。
- [ ] 管理员创建后，即使 bootstrap secret 保持配置或被轮换，也不能再次创建或替换管理员。
- [ ] 日志、数据库、事件和响应不包含 bootstrap secret。

**Impact**: 功能规格 AC-133、运行配置契约、TASK-001、TASK-002、追踪矩阵；Breaking: NO，产品代码尚未实施。

## Testing Strategy

- TASK-001 验证三类进程对缺失、格式错误和复用的 bootstrap secret 一致拒绝启动。
- TASK-002 验证管理员创建后 bootstrap 永久关闭，且日志与持久化不包含 secret。

## Rollback Plan

产品代码尚未实施。若未来要支持移除 bootstrap secret，必须另建变更规格并定义进程如何在不泄露管理员状态的情况下完成数据库感知启动校验。
