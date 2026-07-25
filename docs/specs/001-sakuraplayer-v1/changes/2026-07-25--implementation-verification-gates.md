# Change Specification: 实施验证门禁优化

**Type**: Delta
**Date**: 2026-07-25
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-001 至 TASK-003 的实施证明，重复重建测试镜像、过早重复运行完整 Compose、审计晚于高成本门禁以及共享工作区并发写入会显著增加反馈时间。本变更只优化实施和验证顺序，不改变产品行为、135 条 AC、任务依赖或最终质量下限。

## ADDED

### 分层验证

**Requirements**:

- REQ-CHG-026: 所有未完成任务必须采用 Focused、Fast 和 Final 分层验证；Fast 只用于反馈，不能作为任务完成证据。
- REQ-CHG-027: 完整 Compose 每次 Final 尝试最多运行一次；失败后必须退出 Final，修复并重过受影响的 Fast 与审计，再开始新的 Final 尝试。
- REQ-CHG-028: Final 必须保留任务要求的完整自动测试、真实 PostgreSQL、Compose、安全扫描、恢复和外部门禁，不得因耗时、并行或任务范围而降低。

**Acceptance Criteria**:

- [x] `AGENTS.md`、技术计划、后端测试说明和统一实施流程明确区分 Fast 与 Final。
- [x] 文档明确 Final 失败后的重新进入条件，不允许使用失败前的局部结果完成任务。

### 可复用测试基础设施

**Requirements**:

- REQ-CHG-029: 快速测试应复用无秘密的依赖镜像和专用 PostgreSQL 进程，当前源码必须只读挂载，每次数据库测试必须创建并清理隔离数据库。

**Acceptance Criteria**:

- [x] 测试说明区分已存在命令和待脚本化目标，不声明尚未实现的 `-Gate Fast` 接口。
- [x] 最终 Compose 清理临时应用状态，不把共享构建缓存当作产品状态。

### 单写者并行审计

**Requirements**:

- REQ-CHG-030: 共享工作区只能由主实施路径写文件、迁移数据库、管理容器和操作 Git；子智能体可以并行执行互不依赖的只读审计。

**Acceptance Criteria**:

- [x] 协作规则和架构护栏定义单写者边界以及审计结论的统一修复流程。

### 任务规模复核

**Requirements**:

- REQ-CHG-031: 每个任务开始前必须拆出可独立验证的任务内批次；若需要改变正式任务边界，必须先建立变更规格并同步任务索引、依赖、AC 映射和追踪矩阵。

**Acceptance Criteria**:

- [x] 所有正式任务引用统一实施流程，TASK-004 记录不改变边界的执行批次。
- [x] 任务内批次不产生额外完成状态或 Git 提交，不替代正式 `TASK-xxx`。

## MODIFIED

无产品行为修改。现有产品规格、OpenAPI、错误码、数据模型和 135 条 AC 保持不变。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 项目协作与会话交接 | ADDED/MODIFIED | LOW |
| 技术计划与架构护栏 | MODIFIED | LOW |
| 后端测试说明 | MODIFIED | LOW |
| 任务索引与正式任务 | REFERENCE ONLY | LOW |
| 产品契约与数据模型 | NONE | NONE |

## Task Synchronization

- 57 个正式任务全部增加统一流程引用；除下列显式状态校正和 TASK-004 批次外，不改变标题、依赖、AC 映射或实现范围。
- TASK-004 增加任务内执行批次，仍作为一个任务完成和提交。
- TASK-001 至 TASK-003 的历史 frontmatter 从 `implemented` 校正为与 Git/交接一致的 `completed`，不改变实现内容或验收证据。
- 后续若拆分正式任务，必须另建变更规格；本变更不预先创建新任务 ID。

## Testing Strategy

- 扫描 57 个任务的流程引用、ID、依赖和 AC 映射。
- 校验 Markdown 相对链接、变更规格编号和任务索引数量。
- 检查完整文档差异和 `git diff --check`。

## Rollback Plan

可整体回退本治理变更恢复原执行流程；不得只删除 Final 质量要求而保留 Fast 快捷路径。
