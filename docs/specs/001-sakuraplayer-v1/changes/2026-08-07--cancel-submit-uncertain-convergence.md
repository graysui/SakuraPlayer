# Change Specification: TASK-327 取消不确定离线提交必须收敛

**Type**: Delta
**Date**: 2026-08-07
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

真实运行发现：进入 `submit_uncertain` 的任务在 115 端始终查不到对应离线任务时（例如资源已在其他目录离线过导致本次提交未创建新任务、上游未受理但响应不确定、任务被 115 端清理或超出列表分页），用户显式取消只会让任务在 `submit_uncertain` ↔ `cancelling` 之间循环：worker 取消对账仍无唯一匹配，按 REQ-CHG-273 回到 `submit_uncertain`。该状态不由自动 worker 领取且保留 running 容量，两个运行名额被永久占用，后续影片全部排队且无法缓存，取消按钮永远无效。本次变更修改取消语义：**用户确认取消后必须收敛**——取消对账无唯一远端匹配时进入受管清理（`cleaning`），由 TASK-107 证明式删除终结并释放运行名额；不自动重复提交磁力。

## ADDED

- REQ-CHG-330: 用户确认取消 `submit_uncertain`（或 `submitting` 且已持久化 `submit_started_at` 但无 `remote_info_hash`）任务时，worker 只按受管任务目录做一次分页对账；仍无唯一匹配时**进入 `cleaning`**（受管证明式清理），不得回到 `submit_uncertain`。`cleaning` 归就绪容量，运行名额立即释放；远端目录缺失由清理记录 `task_missing` 证据终结，远端目录存在且归属应用则删除，`cache_root` 失联转 `detached`，删除失败转 `cleanup_failed` 可手动重试。多匹配或分页形状不一致仍按既有 `cloud115_protocol_error` 确定性失败处理，不进入 `cleaning`。
- 取消路径不再存在 `CANCELLING -> SUBMIT_UNCERTAIN` 转移；`SUBMIT_UNCERTAIN -> CANCELLING` 保留为取消入口。`restore_submit_uncertain` 实现随之删除。

## MODIFIED

- REQ-CHG-273（[TASK-226 115 离线确认及时性与协议兼容](2026-08-03--task-226-cloud115-offline-confirmation.md)）：取消对账"仍找不到唯一匹配时保留不确定状态"修订为"仍找不到唯一匹配时进入受管清理（`cleaning`）"；"禁止重新提交磁力"与"不得伪装成取消成功"保留——不伪装成功由受管 `cleaning` 的非终态、持久化证明式删除证据与 `cleanup_failed` 显式失败保证，而不是靠取消死循环。
- `data-model.md` 缓存任务状态图与说明：`submit_uncertain` 的取消出口改为 `cleaning`；`cancelling` 不再回退 `submit_uncertain`。
- `contracts/cloud115-port.md` 离线提交与取消章节：无 `info_hash` 的不确定提交在显式取消时只做一次分页对账，仍找不到进入受管清理而非回到 `submit_uncertain`。
- `contracts/error-codes.md` 的 `cloud115_submit_uncertain` 行：等待人工操作更新为取消进入受管清理。
- `2026-07-24--technical-plan.md` 缓存任务状态图同步更新。

## Acceptance Criteria

- [ ] 取消 `submit_uncertain` 任务且远端无唯一匹配时，任务进入 `cleaning` 并由证明式清理终结（`cleaned`/`detached`），运行名额释放；重复取消不再回到 `submit_uncertain`。
- [ ] 远端有唯一匹配任务时仍先 `cancel_offline` 再进入 `cleaning`；`cloud115_offline_task_not_found` 幂等完成（既有行为不变）。
- [ ] 不自动重复提交磁力；`submit_uncertain` 仍不由自动 worker 领取，只由显式取消推进。
- [ ] 2/10/20 容量、claim fencing、60 秒客户端观察、13 状态文案与 Windows 取消入口/二次确认行为不变。

## Task Synchronization

本变更创建独立实现任务 `TASK-327`，依赖 TASK-104、TASK-107、TASK-226；不新增产品 AC，只修订 AC-086/AC-097 的运行实现语义（确认取消必须收敛、运行中任务可被用户取消并释放名额）。TASK-226 的历史验收条件行同步修订并引用本变更。

## Testing Strategy

- worker 单元测试：取消不确定无匹配 → `cleaning`；有匹配 → 先 `cancel_offline` 再 `cleaning`；`cloud115_offline_task_not_found` 幂等。
- 状态机测试：`CANCELLING` 不再允许 `SUBMIT_UNCERTAIN`；`SUBMIT_UNCERTAIN -> CANCELLING` 保留。
- Fast 运行相关 Ruff、cache/worker 测试及差异/秘密检查；默认测试不访问真实 115。

## Rollback Plan

TASK-327 提交可整体回退；不得通过恢复"取消无效死循环"来处理真实失败。回退需同时恢复 REQ-CHG-273 原文、`restore_submit_uncertain` 实现与 `CANCELLING -> SUBMIT_UNCERTAIN` 转移。
