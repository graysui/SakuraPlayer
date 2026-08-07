# Change Specification: TASK-329 清理 busy 不失败、释放 claim 轮转重试

**Type**: Delta
**Date**: 2026-08-07
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

v1.0.6 后用户报告：手动批量删除 115 缓存文件后，115 后台删除队列长时间繁忙（删除/还原/移动
互斥串行），cleanup worker 对 `cloud115_operation_busy` 只退避重试 3 次（15 秒）后转
`cleanup_failed`，任务反复失败"卡住"；115 网页端手动删除同样被互斥阻塞。`operation_busy` 是
暂时性错误（等 115 删除队列完成后必然可重试成功），本次变更把 busy 处理改为**不失败**：
保持任务 `cleaning`、释放 claim 并按 `updated_at` 轮转，由后续 claim 持续重试直至收敛；
既有 3 次短退避保留用于吸收瞬时互斥。

## ADDED

- REQ-CHG-335: cleanup worker 对 `cloud115_operation_busy` 不转 `cleanup_failed`——保持任务
  `cleaning` 状态、释放 claim 并把 `updated_at` 置为当前时间（`claim_next` 对 CLEANING 按
  `updated_at ASC` 排序，任务排到队尾公平轮转），下次 claim 继续重试；重试历史由重新 claim
  时 running attempt 标记 failed 并新建 attempt 保留证据。`cleaning` 归就绪容量且清理成功
  前不释放（既有语义），但不再因 115 暂时互斥永久停在 `cleanup_failed`。

## MODIFIED

- REQ-CHG-332（TASK-328）：busy 退避重试耗尽后的行为从"转 `cleanup_failed`"修订为"释放
  claim 保持 `cleaning` 轮转重试"；`cloud115_operation_busy` 从 cleanup 失败集合移入"可重试
  暂态"集合。
- `contracts/error-codes.md` 的 `cache_cleanup_failed` 行：补充说明 `cloud115_operation_busy`
  由 worker 保持 cleaning 轮转重试吸收。

## Acceptance Criteria

- [ ] 删除互斥长时间繁忙（`cloud115_operation_busy`）时，任务保持 `cleaning` 且 claim 被释放，
      不转 `cleanup_failed`；115 队列完成后删除成功或证明式终结（目录缺失/已删除幂等）。
- [ ] 多个 busy 任务按 `updated_at` 轮转，不饿死其他清理任务。
- [ ] 重新 claim 保留重试证据（running attempt 标 failed + 新建 attempt）。
- [ ] 非 busy 错误（unavailable/rate_limited/credentials_expired/protocol_error 等）语义不变。

## Task Synchronization

本变更创建独立实现任务 `TASK-329`，依赖 TASK-328；不新增产品 AC。TASK-328 的
`_delete_with_busy_retry` 保留 3 次短退避，仅把耗尽后的出口改为释放轮转。

## Testing Strategy

- worker 单元测试：busy 持续 → 任务保持 `cleaning`、claim 清除、attempt 记录失败；busy 恢复后
  重新 claim 删除成功；多个 busy 任务轮转顺序按 updated_at。
- Fast 运行相关 Ruff、cache/cleanup 测试及差异/秘密检查；默认测试不访问真实 115。

## Rollback Plan

TASK-329 提交可整体回退；不得通过恢复"busy 立即 fail"处理真实互斥。回退需恢复 REQ-CHG-332
原文与 fail 出口。
