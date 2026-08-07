---
id: TASK-329
title: "清理 busy 不失败、释放 claim 轮转重试"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-328]
ac-mapping: [AC-097, AC-122]
imp-requirements: [REQ-018]
cross-boundary: false
external-dependency-risk: true
provides: [cleanup busy release and rotation]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

**变更规格**: [清理 busy 不失败、释放 claim 轮转重试](../changes/2026-08-07--cleanup-busy-release-retry.md)

# TASK-329: 清理 busy 不失败、释放 claim 轮转重试

**功能描述**: 修复批量清理时 115 删除互斥繁忙导致的任务反复 `cleanup_failed`：`cloud115_operation_busy`
不失败，保持任务 `cleaning`、释放 claim 按 `updated_at` 轮转重试，直到 115 队列完成后收敛。

**规格映射**: AC-097、AC-122（运行实现细节修订，无新增 AC）

## 验收条件

- [x] 删除互斥长时间繁忙时，任务保持 `cleaning` 且 claim 被释放，不转 `cleanup_failed`；
      115 队列完成后删除成功或证明式终结。
- [x] 多个 busy 任务按 `updated_at` 轮转，不饿死其他清理任务。
- [x] 重新 claim 保留重试证据（attempt 以 `cloud115_operation_busy` 记 failed + 新建 attempt）。
- [x] 非 busy 错误（unavailable/rate_limited/credentials_expired/protocol_error）语义不变。
- [x] busy 轮转超过上限（`_BUSY_MAX_ATTEMPTS=60`）转 `cleanup_failed` 供用户干预。

## Definition of Ready

- [x] 用户已报告 v1.0.6 后清理反复失败、115 网页手动删除也被互斥阻塞；现场现象已复核。
- [x] p115client 确认删除互斥为暂时性错误、需要持续重试；TASK-328 的 3 次退避不足。
- [x] 已创建并接受 Delta 变更规格，未静默修改冻结规格。

## 实施批次

1. `CleanupQueue.release(claim)`：保持 `cleaning`、清 claim、`updated_at=now`。
2. `CleanupWorker._process`：捕获 `cloud115_operation_busy` → `release`（不 fail）；
   `_delete_with_busy_retry` 保留 3 次短退避。
3. 更新 `test_safe_cleanup.py`：busy 持久测试改为"保持 cleaning + 释放 + 轮转恢复成功"。
4. 同步契约（error-codes）、追踪矩阵与交接；Focused/Fast/审计后提交。

## 实现文件（仅文件名）

**修改**:

- `backend/src/sakuraplayer/cloud_cache/cleanup.py` - release 方法 + busy 分支。
- `backend/tests/unit/cloud_cache/test_safe_cleanup.py` - busy 持久/轮转回归。
- `docs/specs/001-sakuraplayer-v1/contracts/error-codes.md`、`traceability-matrix.md`、
  `SESSION-HANDOFF.md` - 契约与交接同步。

**创建**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-07--cleanup-busy-release-retry.md` - Delta 变更规格。

## Definition of Done

- [x] 所有验收条件、Focused/Fast 和完整差异审计通过。
- [x] 任务状态、实现证据、变更规格、契约、追踪矩阵和交接文档同步。
- [x] 只暂存 TASK-329 相关文件并创建一次中文 Git 提交。

## 完成证据

- Focused：`test_safe_cleanup.py` 11 项通过（新增 busy 轮转公平性、轮转上限、释放后恢复）；
  Ruff 全仓 check 通过。
- Fast：`958 passed, 11 deselected`（98s）。
- `git diff --check` 通过。只读审计（review）：无 blocking；should-fix 已落实——release 无限轮转
  加 `_BUSY_MAX_ATTEMPTS=60` 上限、attempt 以 `cloud115_operation_busy` 记录区分真实失败、
  补充多任务轮转公平性测试。
- 未重跑完整 Compose：本任务仅改 Python 领域逻辑与单元测试，无 Schema/迁移/配置变化，
  Fast 全量自包含与上一发布（v1.0.6）的 Final 已覆盖 PostgreSQL 集成路径；记录此例外。

**依赖**: TASK-328
