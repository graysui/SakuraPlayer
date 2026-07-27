# Change Specification: TASK-015 清理范围与等价门禁

**Type**: Delta
**Date**: 2026-07-27
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-015 原任务允许前序任务处于 `reviewed/implemented`，把清理范围交给仅覆盖
TASK-014 E2E 文件的评审报告，并要求执行尚未锁定的格式、类型和等价检查。它还直接
引用通用清理技能对“目标任务已有评审文件”的假设，而 TASK-015 本身是独立清理任务。
这些条件无法同时满足仓库工作流。本变更只补齐可执行门禁，不扩大清理或产品范围。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 3 |
| MODIFIED | 2 |
| REMOVED | 0 |

## ADDED

### 可重建的清理清单

**Requirements**:

- REQ-CHG-120: 清理输入以 TASK-001 首提交父节点至 TASK-014 完成提交的 Git 区间
  `41d8df6^..66e5b2c` 审批，并与 TASK-001 至 TASK-014 的完成任务和 TASK-014
  `passed` 评审共同确认；容器内质量脚本扫描该区间批准且当前仍存在的 Python 路径，
  不依赖测试镜像中不存在的 Git CLI。
- REQ-CHG-121: 可格式化和 lint 的范围只包括该区间内当前仍存在的
  `backend/src/**/*.py`、`backend/tests/**/*.py` 与 `backend/alembic/env.py`。
  `backend/alembic/versions/*`、产品契约、Schema 和依赖版本不属于卫生修改范围。

**Acceptance Criteria**:

- [x] 质量脚本能输出去重、排序后的实际清理清单，且与固定 Git 区间批准范围一致。
- [x] 完整差异中没有迁移历史、产品契约或业务逻辑变更。

### 锁定的 Python 质量工具链

**Requirements**:

- REQ-CHG-122: Python 3.10.16 测试镜像固定安装 Ruff 0.16.0 和 mypy 2.3.0；
  不使用宿主偶然安装的 Python 或未锁定工具。
- REQ-CHG-123: 格式门禁为
  `ruff format --no-cache --check src tests alembic/env.py`；lint 门禁为
  `ruff check --no-cache src tests alembic/env.py`，规则固定为 `E4,E7,E9,F,I`，
  显式忽略可能改变可观察名称与追踪信息的 `E731`。
- REQ-CHG-124: 既有全量 mypy 基线不作为纯卫生任务的隐式重构范围。类型门禁只覆盖
  发生语义级卫生修改的生产文件；格式或 import 排序本身不扩展类型检查清单。只读
  仓库挂载下必须使用容器临时缓存 `--cache-dir=/tmp/task015-mypy-cache`。

**Acceptance Criteria**:

- [x] 测试镜像报告 Ruff 0.16.0 与 mypy 2.3.0。
- [x] format、lint 与任务声明的渐进类型命令全部通过。

### 可复现的清理前后等价基线

**Requirements**:

- REQ-CHG-125: 仓库提供只读质量脚本，规范化捕获实际 FastAPI OpenAPI、全部既有
  Alembic migration 文件摘要，以及 SQLAlchemy `CheckConstraint` 和元数据阶段/优先级
  定义。基线写入 `.planning/TASK-015/`，不得提交。
- REQ-CHG-126: 基线必须在卫生修改前捕获，在 Fast/审计收敛后重新捕获并由同一脚本
  比较；任一差异都必须停止 Final。
- REQ-CHG-127: 测试行为等价由完整自包含测试、PostgreSQL integration/E2E 和同一次
  Compose Final 证明，不以摘要比较替代执行测试。

**Acceptance Criteria**:

- [x] 清理前后 OpenAPI、迁移和状态机基线逐项相等。
- [x] Fast 与 Compose Final 按统一工作流通过。

## MODIFIED

### TASK-015 Definition of Ready

**Previous Behavior**: TASK-014 为 `reviewed/implemented` 且有 review 文件即可开始，
与清理任务前序必须 `completed` 的统一工作流冲突。

**New Behavior**: TASK-014 必须为 `completed`、正式评审为 `passed`，且 Git HEAD 与
固定清理区间终点一致；TASK-001 至 TASK-014 的实际清单可由质量脚本重建。

### 通用清理流程适配

**Previous Behavior**: TASK-015 直接继承通用清理技能要求目标任务自身已有 review
文件的假设，但独立 cleanup task 在清理结束前没有自身 review。

**New Behavior**: TASK-015 以 TASK-014 的批准评审作为前序行为基线，以本变更的 Git
清单作为清理输入；TASK-015 自身通过 Fast、完整差异自审、只读审计和 Final 后完成。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-015 / backend task index | MODIFIED | LOW |
| Python test toolchain | ADDED | LOW |
| cleanup baseline script | ADDED | LOW |
| product API / Schema / migrations | UNCHANGED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。TASK-015、后端与总任务索引、追踪说明、测试工具链、
测试 README 和 ADR-003 在 TASK-015 同一中文提交中同步。

## Testing Strategy

- 质量脚本测试覆盖清单边界、实际 OpenAPI、迁移摘要、状态约束和相等/不等比较。
- 在卫生修改前后分别捕获 `.planning/TASK-015/cleanup-baseline-*.json`。
- 运行锁定 format/lint、渐进 mypy、Fast、完整差异审计和 Compose Final。

## Rollback Plan

TASK-015 提交前可整体回退本变更、工具链和卫生差异。提交后若质量工具需要变更，
必须以前向 ADR/变更规格更新版本和门禁；不得借回退工具绕过已经发现的行为差异。
