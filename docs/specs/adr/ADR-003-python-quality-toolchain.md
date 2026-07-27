# ADR-003: 锁定 Python 卫生清理质量工具链

**日期**: 2026-07-27
**状态**: Accepted

## 背景

TASK-015 要求运行 Python formatter、linter 和类型检查，但仓库此前只锁定 pytest，
宿主 Python 3.14.6 也不符合项目 Python 3.10.16 基线。未锁定工具会让同一清理在不同
机器产生不同差异或结果。全量 mypy 当前还包含跨多个历史任务的既有类型债务，直接把
它作为纯卫生清理门禁会把任务变成无授权的跨模块重构。

## 决策

在现有 Python 3.10.16 测试镜像的 `test` extra 中固定 Ruff 0.16.0 和 mypy 2.3.0。
Ruff 负责 `backend/src`、`backend/tests` 与 `backend/alembic/env.py` 的确定性格式和
import/lint 检查；历史迁移文件不格式化。mypy 采用渐进门禁，只检查本次发生语义级
卫生修改的生产文件。所有命令使用只读仓库挂载，不依赖宿主 Python 环境。

## 后果

- 修改质量依赖或 Dockerfile 后必须重建测试镜像，Final 也会使用同一锁定版本。
- Ruff 格式化会产生较大的机械差异，必须通过基线比较、完整测试和人工差异审计证明
  行为不变。
- 纯 import 排序不扩大 mypy 范围；新类型债务不能借渐进策略进入被检查文件。
- 后续若要启用全量 mypy，需独立任务清理既有类型基线并更新本 ADR。

## 替代方案

- 使用宿主全局 Ruff/mypy：版本和 Python 运行时不可复现，拒绝。
- 在 TASK-015 修复全部既有 mypy 错误：越过纯卫生边界且风险过大，拒绝。
- 只运行 formatter、不运行 lint 或类型检查：不满足任务验收条件，拒绝。
