# Change Specification: TASK-226 115 离线确认及时性与协议兼容

**Type**: Delta
**Date**: 2026-08-03
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

真实运行中发现：115 已在 1 至 3 秒内完成离线，但 worker 仍以较长间隔确认，导致 Windows 播放等待明显延迟；部分真实任务在离线列表状态解析或提交结果对账时进入 `cloud115_protocol_error` / `cloud115_submit_uncertain`。本变更只修复后端确认反馈和 Cloud115 适配器对等价状态字段的兼容，不缩短客户端既有 60 秒安全观察窗口，不自动重复提交不确定的离线请求。

## ADDED

- REQ-CHG-271: `offlining` 任务在远端仍未完成时的下一次确认目标间隔为不超过 2 秒，cache worker 空闲等待不得再次引入 5 秒固定延迟；该间隔只影响状态观察，不改变 115 请求超时、限流退避或任务状态机。
- REQ-CHG-272: Cloud115 适配器必须把协议上等价的离线状态表示归一化为 `queued/running/completed/failed`；未知状态、缺失必要身份字段和不安全的结构仍返回 `cloud115_protocol_error`，不得把未知值猜测为完成。
- REQ-CHG-273: `submit_uncertain`、取消和重启对账继续只允许按受管任务目录确认；找不到唯一匹配任务时保留不确定状态，禁止重新提交磁力或伪装成取消成功。

## MODIFIED

- REQ-CHG-274: TASK-104 的 offline worker 轮询实现增加短反馈间隔和回归测试；解析 consumer 不得改变 claim fencing、2/10 容量或失败不自动重试语义。
- REQ-CHG-275: TASK-101 的离线任务解析允许已观察的字符串/数字等价状态和兼容字段别名，但稳定 DTO 不增加原始响应、磁力、Cookie、errno 或上游正文。

## Acceptance Criteria

- [ ] 115 离线任务在 1 至 3 秒内完成时，Fake worker 能在不超过 2 秒的下一次观察窗口内进入 `resolving`，并且不重复调用 `submit_offline`。
- [ ] 完成、排队、运行和失败的数字/字符串状态按稳定 DTO 正确归一化；未知状态仍为 `cloud115_protocol_error`。
- [ ] 提交超时或结果不确定的任务仍只进行安全对账；无唯一目录匹配时保持 `submit_uncertain`，取消后不伪造终态。
- [ ] Windows 既有 60 秒等待、迟到 ready 不自动播放、通知和固定 UA 行为不变。

## Task Synchronization

本变更创建独立实现任务 `TASK-226`，依赖 TASK-101、TASK-104、TASK-105、TASK-112；不新增产品 AC，只补强 AC-084、AC-086 至 AC-091 的运行实现证据。TASK-214 的清理任务依赖补入 TASK-226，避免在行为修复前进行卫生收尾。

## Testing Strategy

- 适配器单元测试覆盖数字/字符串等价状态、兼容字段、未知状态和敏感字段不外泄。
- worker 单元/集成测试覆盖 2 秒轮询 claim、完成确认、提交不确定对账和不重复提交。
- Fast 运行相关 Ruff、Cloud115/cache/worker 测试及差异/秘密检查；Final 运行完整 Compose，不访问真实 115。
- TASK-213 的真实 115 门禁仍是显式外部验证，不在默认测试中启用。

## Rollback Plan

TASK-226 提交可整体回退；不得通过回退到重复提交或放宽未知状态校验来处理真实失败。
