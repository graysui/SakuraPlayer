---
id: TASK-015
title: "后端基础与元数据代码清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-014]
ac-mapping: []
imp-requirements: []
cross-boundary: false
external-dependency-risk: false
provides: [reviewed backend foundation and metadata files]
---

# TASK-015: 后端基础与元数据代码清理

**功能描述**: 在 TASK-001 至 TASK-014 全部评审通过后，按 `specs-code-cleanup` 执行纯卫生清理，不改变逻辑或公共签名。

## 验收条件

- [ ] 只处理评审报告列出的后端基础、资源、目录、发现、事件和测试文件。
- [ ] 移除 debug `print`、临时注释、无用 import 和明显不可达代码，保留仍有效且有上下文的 TODO。
- [ ] 运行 `ruff format`、`ruff check`、类型检查和完整 backend 测试；任何失败立即停止。
- [ ] 清理前后 OpenAPI、数据库迁移、状态机和测试行为一致。

## Definition of Ready

- [ ] TASK-014 状态为 reviewed/implemented 且有批准的 review 文件。
- [ ] TASK-001 至 TASK-014 的变更文件清单完整。
- [ ] 当前测试基线全部通过。

## 技术上下文

- 使用 `specs-code-cleanup` 八阶段流程。
- 清理不是重构、bug fix 或依赖升级。
- Python 格式/检查使用项目锁定的 ruff 命令；不在清理中改迁移历史。

## 实现文件（仅文件名）

**修改**:

- `backend/` - 仅限评审报告列出的文件。
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-015.md` - 追加 Cleanup Summary。

## 测试说明

**最终验证**:

- 扫描 `print(`、`# DEBUG`、临时文件、未使用 import 和超过 120 字符的行。
- 执行 formatter/linter/type checker、单元、集成和 TASK-014 E2E。
- 比较 OpenAPI 和迁移签名，确认无功能变化。

## Definition of Done

- [ ] 清理仅包含卫生改动。
- [ ] 所有验证重新通过。
- [ ] 任务追加 Cleanup Summary 并进入 completed。

**依赖**: TASK-014

**实现命令**:

`/developer-kit-specs:specs-code-cleanup --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-015.md"`
