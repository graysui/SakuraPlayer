# Change Specification: 实施技能约束

**Type**: Delta
**Date**: 2026-07-26
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

本变更明确 SakuraPlayer 的实施与验证不使用 Superpowers 插件或其下属技能，避免外部插件工作流与仓库已冻结的 Focused/Fast/Final、单写者和提交门禁产生双重规则。复杂任务继续使用 `planning-with-files-zh` 保存本地执行上下文。本变更不修改产品行为、验收条件、任务依赖或最终质量下限。

## ADDED

### 实施技能边界

**Requirements**:

- REQ-CHG-060: 所有正式任务、缺陷修复和文档维护均不得调用或依赖 Superpowers 插件及任何 `superpowers:*` 技能；规划、TDD、调试、评审、验证、工作树和 Git 收尾以仓库协作规则及统一实施工作流为准。
- REQ-CHG-061: 预计超过 5 次工具调用、包含多个阶段或可能跨会话的工作继续使用 `planning-with-files-zh`；其本地记录不得替代正式任务、契约或 Git 完成证据，也不得纳入任务提交。

**Acceptance Criteria**:

- [x] `AGENTS.md`、统一实施工作流、技术计划、架构护栏、追踪矩阵和会话交接明确一致的插件与技能边界。
- [x] 57 个正式任务继续通过统一实施工作流继承该约束，无需复制规则或修改 AC 映射。
- [x] 全仓文档扫描不存在把 Superpowers 插件或其下属技能声明为可用实施依赖的内容。

## MODIFIED

无产品行为修改。现有功能规格、OpenAPI、错误码、数据模型、任务依赖和 135 条 AC 保持不变。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 项目协作与会话交接 | MODIFIED | LOW |
| 统一实施工作流 | MODIFIED | LOW |
| 技术计划与架构护栏 | MODIFIED | LOW |
| 任务与产品契约 | REFERENCE ONLY | NONE |

## Task Synchronization

- 57 个正式任务已经引用统一实施工作流，因此自动继承本约束，不修改任务状态、依赖、AC 映射或实现范围。
- 本变更不创建 `TASK-CHG`，不改变 TASK-009 的 Definition of Ready 或后续任务顺序。

## Testing Strategy

- 全仓扫描 Superpowers 品牌名、`superpowers:*` 前缀及已知下属技能别名，确认只剩明确的禁用说明。
- 核对 57 个正式任务均引用统一实施工作流。
- 检查 Markdown 相对链接、变更规格编号、完整文档差异和 `git diff --check`。

## Rollback Plan

若未来需要重新引入外部工作流插件，必须新增变更规格，明确其与仓库门禁、单写者和 `planning-with-files-zh` 的优先级；不得只删除禁用文字后静默启用。
