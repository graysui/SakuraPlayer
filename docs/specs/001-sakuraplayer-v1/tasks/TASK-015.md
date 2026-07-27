---
id: TASK-015
title: "后端基础与元数据代码清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
reviewed_date: 2026-07-27
dependencies: [TASK-014]
ac-mapping: []
imp-requirements: []
cross-boundary: false
external-dependency-risk: false
provides: [reviewed backend foundation and metadata files]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-015: 后端基础与元数据代码清理

**功能描述**: 在 TASK-001 至 TASK-014 全部完成且 TASK-014 正式评审通过后，按 `specs-code-cleanup` 执行纯卫生清理，不改变逻辑或公共签名。

**清理门禁**: [TASK-015 清理范围与等价门禁](../changes/2026-07-27--task-015-cleanup-gates.md)

## 验收条件

- [x] 只处理固定 Git 区间重建清单内的后端基础、资源、目录、发现、事件和测试 Python 文件。
- [x] 移除 debug `print`、临时注释、无用 import 和明显不可达代码，保留仍有效且有上下文的 TODO。
- [x] 运行 `ruff format`、`ruff check`、类型检查和完整 backend 测试；任何失败立即停止。
- [x] 清理前后 OpenAPI、数据库迁移、状态机和测试行为一致。

## Definition of Ready

- [x] TASK-014 状态为 `completed` 且正式 review 为 `passed`。
- [x] TASK-001 至 TASK-014 的变更文件可由 `41d8df6^..66e5b2c` 完整重建。
- [x] TASK-014 Final 基线为自包含 466 项、PostgreSQL integration/E2E 88 项通过。

## 技术上下文

- 使用 `specs-code-cleanup` 八阶段流程；独立 cleanup task 的 review 前置按清理门禁变更规格适配。
- 清理不是重构、bug fix 或依赖升级。
- Python 3.10.16 测试镜像锁定 Ruff 0.16.0 与 mypy 2.3.0；不在清理中改迁移历史。
- Ruff 范围为 `src tests alembic/env.py`，lint 规则为 `E4,E7,E9,F,I` 并忽略 `E731`。
- mypy 只检查发生语义级卫生修改的生产文件，不把既有全量类型债务带入本任务。
- 渐进 mypy 文件为 `identity/secrets.py`、`resources/avdb_release.py` 和
  `worker/rankings.py`，缓存写入 `/tmp/task015-mypy-cache`。

## 实现文件（仅文件名）

**修改**:

- `backend/src/`、`backend/tests/`、`backend/alembic/env.py` - 仅限清理 manifest 中的 Python 文件。
- `backend/pyproject.toml`、`backend/tests/README.md` - 锁定并记录质量入口。
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-015.md` - 追加 Cleanup Summary。

**创建**:

- `backend/tests/quality/task015_cleanup_gate.py` - manifest 与 OpenAPI/迁移/状态机等价比较。
- `backend/tests/quality/test_task015_cleanup_gate.py` - 质量入口回归测试。
- `docs/specs/001-sakuraplayer-v1/changes/2026-07-27--task-015-cleanup-gates.md` - 可执行清理边界。
- `docs/specs/adr/ADR-003-python-quality-toolchain.md` - 锁定 Python 质量工具链。

## 测试说明

**最终验证**:

- 扫描 `print(`、`# DEBUG`、临时文件、未使用 import 和超过 120 字符的行。
- 执行 formatter/linter/type checker、单元、集成和 TASK-014 E2E。
- 使用 `tests/quality/task015_cleanup_gate.py` 比较清理前后 OpenAPI、迁移和状态机签名。

## Definition of Done

- [x] 清理仅包含卫生改动。
- [x] 所有验证重新通过。
- [x] 任务追加 Cleanup Summary 并进入 completed。

## Cleanup Summary

- 固定 Git 区间与容器 manifest 一致；Ruff 对批准范围执行确定性格式和 import
  清理，最终 176 个 Python 文件格式合规、lint 全部通过，历史迁移零差异。
- 语义级卫生修改仅移除 `identity/secrets.py` 与 `worker/rankings.py` 的无用 import，
  并在 `resources/avdb_release.py` 以等价 `commit_error` 局部变量保留异常分支语义。
  对应故障注入聚焦测试通过，渐进 mypy 为 3 个生产文件无问题。
- 清理前后实际 FastAPI OpenAPI、13 份 Alembic migration 摘要、SQLAlchemy 状态约束
  和元数据阶段/优先级定义逐项相等；长行、debug/TEMP、TODO/FIXME 和秘密差异扫描
  无问题。AST 审计除已解释的 `commit_error` 外无非 import 语义差异，无剩余 P0/P1/P2。
- Fast 最终为 `469 passed, 8 deselected`，宿主 Docker 断言通过。Compose Final
  首次尝试通过：自包含 `466 passed, 8 deselected`，PostgreSQL integration/E2E
  `88 passed, 15 deselected`；迁移、五服务健康、认证 canary、秘密扫描、重启、ready
  降级恢复和隔离资源清理全部完成。

**依赖**: TASK-014

**实现命令**:

`/developer-kit-specs:specs-code-cleanup --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-015.md"`
