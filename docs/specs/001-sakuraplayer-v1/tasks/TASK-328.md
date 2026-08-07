---
id: TASK-328
title: "缓存清理删除韧性、poll 目录定位与客户端转圈修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-104, TASK-107, TASK-226, TASK-327]
ac-mapping: [AC-086, AC-097, AC-122]
imp-requirements: [REQ-017, REQ-018]
cross-boundary: true
external-dependency-risk: true
provides: [resilient cleanup delete, busy retry, poll directory scoping, in-flight fix]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

**变更规格**: [缓存清理删除韧性、poll 目录定位与客户端转圈修复](../changes/2026-08-07--cache-cleanup-delete-resilience.md)

# TASK-328: 缓存清理删除韧性、poll 目录定位与客户端转圈修复

**功能描述**: 修复 v1.0.5 后清理失败（`cache_cleanup_failed`）与客户端按钮转圈：对照 p115client 扩展
115 删除错误映射（互斥忙 → `cloud115_operation_busy` 退避重试、"已删除" → 幂等成功），
offline 轮询按 `(info_hash, task_cid)` 定位，Windows 缓存页修复 in-flight 残留。

**规格映射**: AC-086、AC-097、AC-122（运行实现细节修订，无新增 AC）

## 验收条件

- [x] 多个任务连续清理时，删除互斥忙被短暂重试吸收，任务最终 `cleaned`/`detached`，不批量 `cleanup_failed`。
- [x] 删除已不存在的目录/文件时清理幂等成功（证明式终结）。
- [x] 同一磁力已在其他目录离线时，`_poll` 按 `(info_hash, task_cid)` 只匹配本任务目录，不歧义失败。
- [x] Windows 缓存页在列表刷新打断在途操作后，按钮不再永久转圈。
- [x] Windows 缓存页"一键清理所有缓存"只对 `awaiting_selection/ready/cleanup_failed` 生效，
      逐个串行请求，单个失败不中断其余，在途期间按钮禁用。
- [x] 2/10/20 容量、claim fencing、取消收敛（REQ-CHG-330）与证明式删除语义不变。

## Definition of Ready

- [x] 用户已报告 v1.0.5 后清理失败、按钮转圈与空目录残留；现场现象已复核。
- [x] 已参考 p115client 确认 115 删除互斥/重试与"已删除"幂等语义；115 允许同磁力重复离线已查证。
- [x] TASK-104/107/226/327 已 completed，offline/cleanup worker 与状态机可用。
- [x] 已创建并接受 Delta 变更规格，未静默修改冻结规格。

## 实施批次

1. adapter 错误映射扩展（`_payload_problem`/`_raise_http_problem` 删除分支）。
2. cleanup worker busy 退避重试。
3. offline `_poll` 按 `(info_hash, task_cid)` 定位。
4. Windows cache_controller in-flight 修复。
5. 后端与 Windows 测试更新 + 回归。
6. 同步契约（error-codes、cloud115-port）、追踪矩阵与交接；Focused/Fast/审计/Final 后提交。

## 实现文件（仅文件名）

**修改**:

- `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/adapter.py` - 删除错误映射。
- `backend/src/sakuraplayer/cloud_cache/cleanup.py` - busy 退避重试。
- `backend/src/sakuraplayer/cloud_cache/worker/offline.py` - poll 目录定位。
- `backend/tests/unit/cloud115/test_adapter_contract.py`、`backend/tests/unit/cloud_cache/test_safe_cleanup.py`、
  `backend/tests/unit/cloud_cache/test_offline_worker.py` - 后端回归。
- `windows/lib/features/cache/presentation/cache_controller.dart` - in-flight 修复。
- `windows/test/features/cache/cache_page_test.dart` - 客户端回归。
- `docs/specs/001-sakuraplayer-v1/contracts/error-codes.md`、`contracts/cloud115-port.md`、
  `traceability-matrix.md`、`SESSION-HANDOFF.md` - 契约与交接同步。

**创建**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-07--cache-cleanup-delete-resilience.md` - Delta 变更规格。

## Definition of Done

- [x] 所有验收条件、Focused/Fast/Windows 测试和完整差异审计通过。
- [x] 任务状态、实现证据、变更规格、契约、追踪矩阵和交接文档同步。
- [x] 只暂存 TASK-328 相关文件并创建一次中文 Git 提交。

## 完成证据

- Focused：adapter/cleanup/offline/state/failure 139 项通过；修复后 cleanup+offline 30 项通过；
  Ruff 全仓 check 通过。
- Windows：`flutter analyze` 无问题；`flutter test test/features/cache/cache_page_test.dart`
  10 项通过（新增 in-flight 刷新、cleanupAll、一键清理 widget 三项）。
- Fast：956 passed、11 deselected；另一次运行中 test_metadata_supervisor 进程回收间歇失败一次，
  单独重跑该文件 14 项通过，确认与本次改动无关。
- `git diff --check` 通过。只读审计（review）：无 blocking；双重 succeed 已修复（返回 bool）；
  offline busy 无限 defer 与既有瞬时退避语义一致记录理由；990009 按 p115client 定为 EBUSY 非认证。
- Final：`backend/tests/run-compose.ps1` 通过（PostgreSQL integration/E2E 全绿，迁移、五服务健康、
  认证、秘密扫描、重启、ready 降级恢复和资源清理完成，默认测试未访问真实 115）。

**依赖**: TASK-104, TASK-107, TASK-226, TASK-327
