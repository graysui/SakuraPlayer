# Change Specification: TASK-328 缓存清理删除韧性、poll 目录定位与客户端转圈修复

**Type**: Delta
**Date**: 2026-08-07
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

真实运行（v1.0.5 后）发现：取消 `submit_uncertain` 任务后清理频繁失败（`cache_cleanup_failed`），
115 端残留空目录，Windows 客户端部分清理按钮一直转圈。对照 [p115client](https://github.com/ChenyangGao/p115client)
的删除实现确认：115 的 `rb/delete` 删除与还原/移动互斥串行，目录删除响应时后台可能仍在执行，
后续删除会返回 `{"state":false,"errno":990009}`（"删除...操作尚未执行完成"）等忙错误，需要
短暂退避重试；"文件已删除，请勿重复操作"（231011 等）应视为幂等成功。我们的错误映射未覆盖
这些 errno，全部落为 `cloud115_protocol_error` 导致 cleanup worker 立即失败。另外 115 允许同一
磁力重复离线到不同目录（不按 info_hash 去重），离线轮询按 info_hash 唯一匹配会在同 hash 多任务时
歧义。本次变更只修复删除错误映射、清理重试、poll 定位与客户端按钮状态，不切换删除接口、
不改变 2/10/20 容量与取消收敛语义。

## ADDED

- REQ-CHG-331: Cloud115 适配器删除操作（`delete_managed_entries`）错误映射扩展——
  "文件/目录不存在或已删除"类 errno（`231011`、`20013`、`20018`、`31003`、`50015`、`70005`、
  `70008`、`90008`、`430004`、`800001`）映射为 `cloud115_file_not_found`（清理幂等成功）；
  "删除/还原/移动尚未执行完成、账号有类似任务正在处理"类 errno（`990009`、`990019`、`990005`）
  映射为新稳定码 `cloud115_operation_busy`。既有 `_NOT_FOUND_ERRNOS` 保留。
- REQ-CHG-332: cleanup worker 对 `cloud115_operation_busy` 在 claim lease 内做短暂退避重试
  （最多 3 次、每次 5 秒），仍失败才转 `cleanup_failed`（可手动重试）；其余错误语义不变。
- REQ-CHG-333: offline worker 轮询（`_poll`）按 `(info_hash, task_cid)` 组合定位远端任务，
  消除同一 info_hash 在多目录重复离线时的唯一匹配歧义；submit 对账仍只按受管任务目录确认。
- REQ-CHG-334: Windows 缓存页新增"一键清理所有缓存"按钮：只对
  `awaiting_selection/ready/cleanup_failed` 状态任务生效（复用单任务清理 API 与二次确认），
  逐个串行请求不并发（天然规避 115 删除互斥），单个失败（如 `cache_active_lease`/`state_conflict`）
  记录错误不中断其余；批量在途期间按钮禁用，完成后刷新列表。

## MODIFIED

- Windows 缓存页控制器：`_act`（取消/清理）与 `selectMedia` 在列表刷新（generation 变化）后
  仍清除对应 job 的 in-flight 状态，`_loadFirstPage` 重置 `inFlightIds`，避免按钮永久转圈。
- `contracts/error-codes.md` 新增 `cloud115_operation_busy` 行；`contracts/cloud115-port.md`
  删除错误表同步。

## Acceptance Criteria

- [ ] 多个任务连续清理时，前一个删除仍在 115 后台执行导致的 `cloud115_operation_busy` 被短暂
      重试吸收，任务最终 `cleaned`/`detached`，不再批量 `cleanup_failed`。
- [ ] 删除已不存在的目录/文件时清理幂等成功（`cloud115_file_not_found` → 证明式终结）。
- [ ] 同一磁力已在其他目录离线时，`_poll` 按 `(info_hash, task_cid)` 只匹配本任务目录的任务，
      不因同 hash 多任务歧义失败。
- [ ] Windows 缓存页在列表刷新打断在途取消/清理/选文件操作后，按钮不再永久转圈。
- [ ] 2/10/20 容量、claim fencing、取消收敛（REQ-CHG-330）与证明式删除语义不变。

## Task Synchronization

本变更创建独立实现任务 `TASK-328`，依赖 TASK-104、TASK-107、TASK-226、TASK-327；不新增产品
AC，只修订 AC-086/AC-097/AC-122 的运行实现细节。取消 `task_del` 按 hash 删除全部同 hash 任务
的 115 能力限制记录为已知边界，不在本变更处理。

## Testing Strategy

- adapter 单元测试：删除操作对 `990009/990019/990005` 映射 `cloud115_operation_busy`；
  `231011/20013/20018/90008/430004/800001` 映射 `cloud115_file_not_found`。
- cleanup worker 测试：busy 重试最多 3 次、退避后成功；仍 busy 转 `cleanup_failed`。
- offline worker 测试：同 hash 两条任务（不同 task_cid）时 `_poll` 只匹配本目录任务。
- Windows controller 测试：刷新打断在途操作后 inFlightIds 清除、按钮不转圈。
- Fast 运行相关 Ruff、cache/worker 测试与差异/秘密检查；Windows `flutter test` 与 analyze；
  默认测试不访问真实 115。

## Rollback Plan

TASK-328 提交可整体回退；不得通过关闭清理重试或放松删除幂等来处理真实失败。回退需同时恢复
错误映射、busy 重试、poll 定位与客户端 in-flight 语义。
