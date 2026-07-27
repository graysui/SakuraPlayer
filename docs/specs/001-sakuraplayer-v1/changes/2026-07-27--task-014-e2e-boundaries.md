# Change Specification: TASK-014 后端元数据 E2E 确定性边界

**Type**: Delta
**Date**: 2026-07-27
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-014 原任务把 Phase 1 后端 E2E 写成全部 AC-001..AC-078，并同时要求真实
API/worker/scheduler 进程、进程内 fake HTTP transport、只新增 E2E 文件、真实 600 秒
等待和重复规格规模性能验证。这些约束与已交付接口、Final runner 和任务边界不能同时
满足。本变更冻结可执行的 Phase 1 E2E 范围，不改变产品行为、公开 API 或生产配置。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 3 |
| REMOVED | 0 |

## ADDED

### Phase 1 后端元数据 E2E 契约

**Requirements**:

- REQ-CHG-113: TASK-014 只验证 TASK-001 至 TASK-013 已交付的 Phase 1 后端切片，
  不声明覆盖 115 扫码/缓存/播放、Windows/HarmonyOS UI、本地字幕或外部门禁。
- REQ-CHG-114: 行为 E2E 使用隔离 PostgreSQL、真实 Alembic head 和生产应用服务组合。
  外部 AVdb/JavDB/DMM/图片/GFriends/AI 在既有显式构造边界注入固定 fake adapter 或
  `httpx.MockTransport`；不得新增生产 fixture 环境变量、任意 provider URL 或测试后门。
- REQ-CHG-115: API/worker/scheduler 的真实容器进程、健康、重启、Schema 门禁和 ready
  降级由同一次 Final 的现有 Compose 流程验证。pytest E2E 不重复启动第二套进程树，
  但必须覆盖 scheduler 生产者、worker consumer/supervisor 和 API 查询所共享的
  PostgreSQL 事实。
- REQ-CHG-116: `backend/tests/e2e` 使用现有 `integration` marker，并由
  `backend/tests/run-compose.ps1` 的 PostgreSQL 测试步骤显式执行。Final runner、测试
  README 和 TASK-014 E2E 文件属于本任务允许修改范围。
- REQ-CHG-117: 600 秒进程组硬终止沿用 TASK-007 Final 证据。TASK-014 从已持久化
  `metadata_timeout` 事实验证管理员手动 retry 会创建独立 attempt、保留父 attempt 且
  不发生自动重试；E2E 不等待真实 600 秒。
- REQ-CHG-118: 289,858 来源与 100,000 别名性能沿用 TASK-005/TASK-011 证据，250 条
  排行榜性能沿用 TASK-012 证据。TASK-014 只在功能规模 fixture 上验证跨边界结果，
  不重复易抖动的大规模 p95 或峰值内存基准。
- REQ-CHG-119: E2E fixture 覆盖成功、429/上游不可用、结构变化、歧义和超时结果；
  报告中的测试 ID 必须包含对应 AC ID。默认套件不得访问真实 115、JavDB 写操作或
  付费 AI，失败输出和日志不得包含磁力、token、密码、API key 或完整能力 URL。

**Acceptance Criteria**:

- [x] 空库迁移后，认证、AVdb 解密/六分类导入、首批入队、元数据核心提交、目录、
  搜索、排行榜、事件和诊断通过同一隔离 PostgreSQL 串联。
- [x] 重复 Release/来源保持幂等，AI 和任一可选元数据源故障不隐藏 core_ready 影片，
  也不清空最近成功排行榜快照。
- [x] `tests/e2e` 在唯一 Final runner 中执行，Compose 仍只运行一次且资源完整清理。
- [x] 未新增生产测试开关、任意外部地址配置、数据库迁移或公开 API 字段。

## MODIFIED

### TASK-014 验证范围

**Previous Behavior**: frontmatter 覆盖 AC-001..AC-078，包含未交付的客户端、115 和
HarmonyOS 行为，并把本工作流全部 `[IMP]` 表述为本任务重新实现或逐项 E2E。

**New Behavior**: TASK-014 验证 Phase 1 后端切片及 AC-023、AC-058、AC-132 的本阶段
观察点。前序任务的 Focused/Fast/Final 是逐项实现证据，TASK-014 只增加跨边界证据。

### Definition of Ready

**Previous Behavior**: TASK-001 至 TASK-013 “已实现并评审”即可开始。

**New Behavior**: 所有前序任务必须为 `completed` 且已有各自中文提交，符合统一工作流
对 E2E 前序状态的要求。

### 测试文件所有权

**Previous Behavior**: TASK-014 只允许新增四个 E2E 文件，现有 Final 不运行它们。

**New Behavior**: 允许修改 Final runner 和测试 README，并可增加固定 E2E fixture；
生产代码、Schema、公开契约和运行配置保持不变。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-014 / Phase 1 E2E scope | MODIFIED | MEDIUM |
| backend metadata E2E contract | ADDED | MEDIUM |
| Final runner / test README | MODIFIED | MEDIUM |
| product API / Schema / runtime config | UNCHANGED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。功能规格引用、架构契约索引、TASK-014、后端任务索引、
追踪矩阵、E2E 契约和 Final runner 在 TASK-014 同一中文提交中同步。

## Testing Strategy

- 自包含契约测试验证 E2E 文件被 Final runner 收集且测试 ID 含 AC ID。
- PostgreSQL E2E 覆盖主链、幂等、可选故障隔离、timeout retry、事件恢复和秘密扫描。
- Final 继续运行完整自包含、全部 PostgreSQL integration/E2E、五服务 Compose、认证
  canary、秘密扫描、重启和 ready 降级恢复。

## Rollback Plan

TASK-014 提交前可整体回退本变更与测试。提交后只移除测试不会改变产品数据；若调整
E2E 范围，必须以前向变更同步任务、契约、runner 和追踪矩阵。
