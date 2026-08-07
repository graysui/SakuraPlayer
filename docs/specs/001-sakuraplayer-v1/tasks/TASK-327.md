---
id: TASK-327
title: "取消不确定离线提交必须收敛"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-104, TASK-107, TASK-226]
ac-mapping: [AC-086, AC-097]
imp-requirements: [REQ-017, REQ-018]
cross-boundary: false
external-dependency-risk: false
provides: [convergent cancel for submit_uncertain]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

**变更规格**: [取消不确定离线提交必须收敛](../changes/2026-08-07--cancel-submit-uncertain-convergence.md)

# TASK-327: 取消不确定离线提交必须收敛

**功能描述**: 修复 `submit_uncertain` 任务取消死循环：用户确认取消后取消必须收敛，进入受管清理（`cleaning`）并由证明式删除终结，释放 running 名额；不再回到 `submit_uncertain`。

**规格映射**: AC-086、AC-097（运行实现语义修订，无新增 AC）

## 验收条件

- [x] 取消 `submit_uncertain` 任务且远端无唯一匹配时，任务进入 `cleaning` 并由证明式清理终结（`cleaned`/`detached`），运行名额释放；重复取消不再回到 `submit_uncertain`。
- [x] 远端有唯一匹配任务时仍先 `cancel_offline` 再进入 `cleaning`；`cloud115_offline_task_not_found` 幂等完成（既有行为不变）。
- [x] 不自动重复提交磁力；`submit_uncertain` 仍不由自动 worker 领取，只由显式取消推进。
- [x] 2/10/20 容量、claim fencing、60 秒客户端观察、13 状态文案与 Windows 取消入口/二次确认行为不变。

## Definition of Ready

- [x] TASK-104/107/226 已 completed，offline worker、cleanup worker 与状态机可用。
- [x] 用户已报告真实死循环故障（取消无效、运行名额被占）；根因已定位到 `_cancel` 的 `restore_submit_uncertain` 分支。
- [x] 已创建并接受 Delta 变更规格，未静默修改冻结规格。
- [x] 回归测试与验证命令已准备。

## 实施批次

1. 修改 `offline.py::_cancel`：无唯一远端匹配 → `complete_cancel`（进入 `cleaning`），删除 `restore_submit_uncertain` 调用。
2. 删除 `claim.py::restore_submit_uncertain` 与 `cache_job.py` 状态机 `CANCELLING -> SUBMIT_UNCERTAIN` 转移。
3. 更新单元测试（`test_offline_worker.py`、`test_cache_state.py`）并新增取消收敛回归。
4. 同步冻结规格文档（data-model、cloud115-port、error-codes、technical-plan、TASK-226、追踪矩阵）。
5. 运行 Focused/Fast、完整差异与只读审计，更新任务状态、交接并创建一次中文 Git 提交。

## 实现文件（仅文件名）

**修改**:

- `backend/src/sakuraplayer/cloud_cache/worker/offline.py` - 取消收敛。
- `backend/src/sakuraplayer/cloud_cache/worker/claim.py` - 删除 `restore_submit_uncertain`。
- `backend/src/sakuraplayer/cloud_cache/domain/cache_job.py` - 状态机移除 `CANCELLING -> SUBMIT_UNCERTAIN`。
- `backend/tests/unit/cloud_cache/test_offline_worker.py` - 取消不确定回归。
- `backend/tests/unit/cloud_cache/test_cache_state.py` - 状态转换更新。
- `docs/specs/001-sakuraplayer-v1/data-model.md`、`contracts/cloud115-port.md`、`contracts/error-codes.md`、`2026-07-24--technical-plan.md`、`tasks/TASK-226.md`、`traceability-matrix.md` - 契约与规格同步。

**创建**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-07--cancel-submit-uncertain-convergence.md` - Delta 变更规格。

## 测试说明

**单元测试**:

- 取消不确定无匹配 → `cleaning`，`submit_offline` 只调用一次。
- 取消不确定有匹配 → 先 `cancel_offline` 再 `cleaning`。
- 状态机：`CANCELLING` 不允许 `SUBMIT_UNCERTAIN`；`SUBMIT_UNCERTAIN -> CANCELLING` 保留。
- 取消收敛后再次取消幂等（`cancelling/cleaning` 幂等）。

**边界条件**:

- `cloud115_offline_task_not_found` 幂等完成；远端目录缺失由 cleanup 证明式终结（既有 TASK-107 行为）。

## Definition of Done

- [x] 所有验收条件、Focused/Fast 和完整差异审计通过。
- [x] 任务状态、实现证据、变更规格、契约、索引、追踪矩阵和交接文档同步。
- [x] 只暂存 TASK-327 相关文件并创建一次中文 Git 提交。

## 完成证据

- Focused：`tests/unit/cloud_cache/test_offline_worker.py` + `test_cache_state.py` 67 项通过；
  `tests/unit/cloud_cache tests/unit/worker` 212 项通过（含审计加固后重跑）。
- Fast：Ruff 全仓 check 通过；自包含 935 passed、11 deselected；`git diff --check` 通过。
- 只读审计：review 子智能体 1 个 should-fix（`run_once` 未捕获 `InvalidCacheJobTransition`）已修复；
  nits 记录不阻塞（`_cancel` 建目录为既有 TASK-104 行为；测试以 `idle` 间接验证名额释放）。
- Final：`backend/tests/run-compose.ps1` 第二次尝试通过——首次尝试 1 项既有失败
  （`test_postgres_catalog_filters_cursor_details_and_images_are_safe`，REQ-CHG-329 排序变更后
  fixture `release_date` 相同导致随机 UUID 平局），已作为独立修复提交处理；重跑后全部通过，
  迁移、五服务健康、认证、秘密扫描、重启、ready 降级恢复和隔离资源清理完成，默认测试未访问真实 115。

**依赖**: TASK-104, TASK-107, TASK-226
