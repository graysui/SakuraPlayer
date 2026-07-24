---
id: TASK-007
title: "持久元数据队列与硬超时"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-001, TASK-005]
ac-mapping: [AC-037, AC-038, AC-039, AC-040, AC-041, AC-042, AC-043, AC-122]
imp-requirements: [REQ-008, REQ-022]
cross-boundary: false
external-dependency-risk: false
provides: [metadata queue, three-slot supervisor, 600-second process timeout]
---

# TASK-007: 持久元数据队列与硬超时

**功能描述**: 实现 PostgreSQL 元数据队列、固定三子进程 supervisor、600 秒进程组硬终止、五级优先级、完整失败重试和可选富化阶段重试。

**规格映射**: AC-037 至 AC-043、AC-122

## 验收条件

- [ ] 元数据任务、阶段和结果持久化，重启可恢复调度；对应 AC-037。
- [ ] 同时执行固定 3 个影片任务，单任务 600 秒由父进程强制终止并标记失败；对应 AC-038、AC-039。
- [ ] 失败/超时不自动创建重试，只有管理员动作生成新 attempt；对应 AC-040。
- [ ] 优先级和同级发布日期排序严格按规格，记录 stage、时间、耗时、尝试和错误；对应 AC-041、AC-043。
- [ ] 核心提交后可见，可选富化失败不回滚；对应 AC-042。
- [ ] `completed_with_warnings` 只允许管理员选择失败/缺失可选阶段创建新 job，禁止 `javdb_core` 和隐式 AI 重跑；对应 AC-122。

## Definition of Ready

- [ ] TASK-005 可提供规范化番号、发布日期和队列原因。
- [ ] 子进程不能共享数据库 session/http client 的边界已确认。
- [ ] queued/running 部分唯一约束和 claim expiry 已迁移。

## 技术上下文

- worker 使用 `FOR UPDATE SKIP LOCKED`；父进程最多维护 3 个子进程组。
- 线程 future 或单纯 `asyncio.wait_for` 不能作为硬终止实现。
- `failed`/warning 行不可复位；retry 新建 `parent_job_id` 指向旧任务，富化重试保存 `retry_mode/requested_stages`。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/metadata_queue.py` - 入队、优先级和手动重试。
- `backend/src/sakuraplayer/worker/metadata_supervisor.py` - 三槽子进程和 600 秒终止。
- `backend/src/sakuraplayer/worker/metadata_child.py` - 单影片 stage runner。
- `backend/src/sakuraplayer/catalog/metadata_state.py` - 合法状态和 stage 记录。
- `backend/tests/unit/catalog/test_metadata_priority.py` - 优先级/去重单测。
- `backend/tests/integration/worker/test_metadata_supervisor.py` - 并发、超时、重启测试。

## 测试说明

**单元测试**:

- 验证五级优先级、同级发布日期降序、同番号只有一条活动任务。
- 验证失败只允许显式 manual retry 新建 attempt；warning 重试只运行白名单 stage，普通 worker 不重排。

**集成测试**:

- 启动超过 3 个阻塞 fixture，验证最多 3 个运行；一个超过 600 秒的可控假时钟任务终止完整进程组并持久失败。
- worker 在 queued/running/core 已提交等阶段崩溃后重启，验证状态和已提交 core 数据可对账。

**边界条件**:

- 600 秒边界、父进程崩溃、claim 过期、手动重试与新搜索并发。

## Definition of Done

- [ ] 固定并发、硬超时、优先级、持久化和手动重试完成。
- [ ] 没有配置元数据并发数的用户入口。
- [ ] 超时/崩溃集成测试通过。

**依赖**: TASK-001, TASK-005

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-007.md"`
