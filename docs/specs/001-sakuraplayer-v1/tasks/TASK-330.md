---
id: TASK-330
title: "缓存任务目录名缩短为 10 字符内无连字符"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-104]
ac-mapping: [AC-080, AC-081]
imp-requirements: [REQ-017]
cross-boundary: false
external-dependency-risk: false
provides: [short cache task directory name]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

**变更规格**: [缓存任务目录名缩短为 10 字符内无连字符](../changes/2026-08-07--cache-task-dir-short-name.md)

# TASK-330: 缓存任务目录名缩短为 10 字符内无连字符

**功能描述**: 新建缓存任务目录名由 `cache-<32hex>`（37 字符）缩短为 `uuid.uuid4().hex[:10]`
（10 字符、无连字符），降低 115 端深层长路径对操作效率的影响；既有任务不迁移。

**规格映射**: AC-080、AC-081（运行实现细节修订，无新增 AC）

## 验收条件

- [x] 新建缓存任务目录名为 10 字符内、不含 `-`、随机且不可由标题控制。
- [x] 既有任务 `task_dir_name` 保持不变，worker/cleanup/ownership 按存储值精确匹配不受影响。
- [x] 短名碰撞概率可接受（40 bit 熵），且创建时按 binding 查重重试（`_unique_task_dir_name`），
      避免同名复用导致数据串扰。

## Definition of Ready

- [x] 用户已报告 `cache-<32hex>` 目录名过长影响 115 效率；现场路径已复核。
- [x] `task_dir_name` 长度 1-128 与"随机不可由标题控制"约束不冲突；无格式强制前缀。
- [x] 已创建并接受 Delta 变更规格，未静默修改冻结规格。

## 实施批次

1. `play_request.py` 创建任务处：`task_dir_name=f"cache-{uuid.uuid4().hex}"` →
   `task_dir_name=uuid.uuid4().hex[:10]`。
2. play_request 创建测试补充短名断言。
3. 同步 data-model、追踪矩阵与交接；Focused/Fast/审计后提交。

## 实现文件（仅文件名）

**修改**:

- `backend/src/sakuraplayer/cloud_cache/play_request.py` - 短目录名生成。
- `backend/tests/unit/cloud_cache/`（play_request 创建相关测试）- 短名断言。
- `docs/specs/001-sakuraplayer-v1/data-model.md`、`traceability-matrix.md`、
  `SESSION-HANDOFF.md` - 规格与交接同步。

**创建**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-07--cache-task-dir-short-name.md` - Delta 变更规格。

## Definition of Done

- [x] 所有验收条件、Focused/Fast 和完整差异审计通过。
- [x] 任务状态、实现证据、变更规格、契约、追踪矩阵和交接文档同步。
- [x] 只暂存 TASK-330 相关文件并创建一次中文 Git 提交。

## 完成证据

- Focused：`test_play_request.py` + `test_offline_worker.py` 33 项通过（新增短名格式断言
  `len==10` 无连字符纯 hex）；Ruff 全仓 check 通过。
- Fast：`959 passed, 11 deselected`（106s）。`git diff --check` 通过。
- 只读审计（review）：minor nits OK to ship；should-fix 已落实——创建时按 binding 查重重试
  （`_unique_task_dir_name`）防止短名碰撞复用目录；既有任务不迁移，worker/cleanup/ownership
  均为值匹配不受格式影响。
- 未重跑完整 Compose：仅领域生成逻辑与单测，无 Schema/迁移变化，记录例外。

**依赖**: TASK-104
