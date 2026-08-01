# SakuraPlayer v1 实施任务总索引

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**技术计划**: [2026-07-24--technical-plan.md](2026-07-24--technical-plan.md)

**实施与验证流程**: [implementation-workflow.md](implementation-workflow.md)

**生成日期**: 2026-07-24

**状态**: Pending

## 1. 代码库分析

- 当前 `player` 仓库只有冻结规格和技术文档，属于从零实现，不存在可直接修改的产品源码或知识图谱缓存。
- 可选择性移植 `avmedia` 中的 Cloud115 SDK、JavDB/DMM provider、GFriends 索引和 Flutter `ThrottlingPlayer`；移植必须保留 GPLv3 来源说明并重新通过本规格测试。
- 后端采用模块化单体，`api/scheduler/worker` 独立进程；PostgreSQL 同时承担持久业务状态、任务队列和事件日志。
- Windows 是 Flutter 单独工程；HarmonyOS 是 API 24 Stage 模型 ArkTS/ArkUI 工程，只共享契约和语义。

## 2. 工作流

| 工作流 | 实现任务 | E2E | 清理 | 进入条件 | 索引 |
|---|---:|---:|---:|---|---|
| 后端基础与元数据 | 15 | 1 | 1 | 无 | [任务列表](2026-07-24--backend-foundation-metadata--tasks.md) |
| 115 缓存与播放后端 | 12 | 1 | 1 | TASK-015 完成 | [任务列表](2026-07-24--cloud115-cache-playback--tasks.md) |
| Windows 客户端 | 14 | 1 | 1 | 后端契约冻结；可用 Fake 115 | [任务列表](2026-07-24--windows-client--tasks.md) |
| HarmonyOS 客户端 | 11 | 2 | 1 | TASK-213 和 AC-130 完成；TASK-312/AC-131 前置探针通过 | [任务列表](2026-07-24--harmonyos-client--tasks.md) |

**合计**: 52 个实现任务、5 个 E2E 任务、4 个清理任务，共 61 个任务。每个工作流的实现任务数不超过 15。

## 3. 关键路径

```text
TASK-001..013
  -> TASK-014 E2E
  -> TASK-015 cleanup
  -> TASK-101..112
  -> TASK-113 E2E
  -> TASK-114 cleanup
  -> TASK-201..212
  -> TASK-213 Windows E2E + real 115
  -> TASK-215 runtime progress UX fixes
  -> TASK-216 provider runtime availability
  -> TASK-218 metadata limited detail and queue controls
  -> TASK-217 initial metadata snapshots
  -> TASK-214 cleanup
  -> TASK-301 API 24 minimal probe scaffold
  -> TASK-312 AC-131 API 24 device preflight
  -> TASK-302..311
  -> TASK-313 HarmonyOS final E2E
  -> TASK-314 cleanup
```

Windows 页面任务可在 Cloud115 后端开发期间使用 OpenAPI fixture 并行，但 Windows 工作流的正式完成路径从已完成的 TASK-114 进入 TASK-201。HarmonyOS 功能实现不能与 Windows 主链路并行提前开始。

## 4. 质量门禁

| 门禁 | 结果/要求 |
|---|---|
| 规格分类 | 128 `[IMP]`、4 `[SEF]`、3 `[EXT]` 已保留 |
| 工作流规模 | PASS；四个工作流分别 15/12/13/11 个实现任务，满足每个工作流不超过 15 个实现任务的约束 |
| 单任务规模 | 开始前按统一流程复核独立行为闭环；工作流任务数不能替代单任务粒度检查 |
| `[IMP]` 覆盖 | 每条 `[IMP]` 至少映射一个实现任务和测试说明 |
| `[SEF]` 覆盖 | 仅放入对应工作流 E2E，不创建独立实现任务 |
| `[EXT]` 覆盖 | AC-130 在 TASK-213；AC-006/131 在 TASK-312 前置门禁 |
| 限界上下文 | CP 任务通过已发布 Port 调用资源/事件模块，不跨上下文直接改表 |
| 外部依赖 | AVdb/JavDB/DMM/GFriends/AI/115 任务显式标记风险和替身策略 |
| 文件冲突 | 每个实现任务拥有独立模块文件；composition skeleton 由脚手架任务一次创建 |
| 测试忠实度 | 阻断测试只来自规格；实现建议只列为补充验证 |

## 5. 文件所有权

| 路径 | 所有工作流 | 规则 |
|---|---|---|
| `backend/src/sakuraplayer/identity` | 后端基础 | 其他上下文只调用公开应用端口 |
| `backend/src/sakuraplayer/resources` | 后端基础 | 115 确定性拒绝通过 `SourceRejectionPort` 调用 |
| `backend/src/sakuraplayer/catalog` | 后端基础 | 客户端只经 REST 访问 |
| `backend/src/sakuraplayer/discovery` | 后端基础 | 榜单不在页面打开时抓取 |
| `backend/src/sakuraplayer/cloud_cache` | 115 后端 | 只通过 `Cloud115Port` 访问 115 |
| `backend/src/sakuraplayer/playback` | 115 后端 | 不持久化上游短链或字幕正文 |
| `windows/lib/features/*` | Windows | 每个 feature 任务拥有自己的目录 |
| `harmony/entry/src/main/ets/features/*` | HarmonyOS | 使用 Stage 模型和 Navigation |

E2E 任务只创建独立测试文件。清理任务按规范顺序在评审后处理所有已变更文件，属于强制收尾，不新增或改变功能。

## 6. 执行规则

1. 按依赖顺序实现，任务状态使用 `pending -> in_progress -> implemented -> reviewed -> completed`；状态进入条件见统一流程。除显式外部门禁外，依赖任务达到 `completed` 后才放行下游任务。
2. 每个任务实现与 Fast 完成后先评审，再进入 Final；工作流 E2E 完成后才运行该工作流的清理任务，清理不得修复逻辑或改变签名。
3. 默认测试不得访问真实 115、JavDB 写操作或付费 AI；真实测试只在明确 E2E 门禁运行。
4. 任何任务发现规格冲突时停止实现并更新规格/技术计划，不能在代码中静默选择。
5. 需求到任务的逐条映射见 [traceability-matrix.md](traceability-matrix.md)。
6. 每个任务开始前先拆出可独立验证的任务内批次；统一使用 Focused/Fast/Final 分层门禁。任务边界需要变化时，先建立变更规格并同步本索引、依赖和追踪矩阵。
7. `cross-boundary: false` 表示任务不直接修改其他上下文拥有的数据或内部实现；通过已发布 Port 协调多个上下文仍可为 `false`。需要共同修改多个上下文所有权边界时必须标为 `true` 并先复核任务粒度。

## 7. 首个执行命令

```text
/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-001.md"
```
