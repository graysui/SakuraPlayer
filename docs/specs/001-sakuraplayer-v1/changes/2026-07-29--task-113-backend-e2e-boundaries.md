# Change Specification: TASK-113 115 缓存播放后端 E2E 边界

**Type**: Delta
**Date**: 2026-07-29
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-113 原任务把后端 Fake E2E 写成整个缓存播放工作流所有 `[IMP]` 的重新证明，并直接要求
验证 60 秒客户端倒计时、全屏等待、播放器菜单、自动播放与 UI 角标。它同时把跨身份配置、
资源接入、目录发现、115 缓存、播放和事件的任务标记为非跨边界，并假设现有 Fake 已有可查询
远端状态。TASK-112 完成后生产接口已经具备组合条件，但这些任务描述仍无法由后端测试诚实满足。

本变更冻结 TASK-113 的后端可观察证据、状态化 Fake 和 Final 归属，不改变产品行为、Schema、
公开 API、Cloud115Port 或运行配置。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 2 |
| MODIFIED | 4 |
| REMOVED | 0 |

## ADDED

### Phase 2 后端 E2E 契约

**Requirements**:

- REQ-CHG-137: TASK-113 必须使用隔离 PostgreSQL、真实 Alembic head、生产应用服务/仓储/worker
  pipeline 和 Fake Cloud115Port 组合，禁止复制生产状态机或增加生产测试开关。
- REQ-CHG-138: pytest E2E 只组合进程内服务；真实 API/worker/scheduler 容器、启动恢复、健康、
  ready 降级和资源清理由同一次 Compose Final 证明，不启动第二套进程树。
- REQ-CHG-139: 测试必须按场景断言 PostgreSQL、领域事件/通知、公开 API/快照和 Fake 远端状态；
  不要求每个断言同时读取所有四方，但每个关键状态转换至少有数据库和一个公开观察面证据。
- REQ-CHG-140: E2E 测试 ID 必须包含对应 AC ID；前序 TASK-101 至 TASK-112 的逐项测试仍是各
  `[IMP]` 实现证据，TASK-113 只增加代表性跨边界组合证据。

**Acceptance Criteria**:

- [x] 从空库迁移后可串联扫码绑定、受管根、来源播放请求、离线、解析/选择、播放、字幕、进度、
  通知/快照和证明式清理。
- [x] 默认 E2E 不访问真实 115、JavDB 写操作或付费 AI，不新增 Schema、公开 API 或生产配置。

### 状态化 Fake115 测试模型

**Requirements**:

- REQ-CHG-141: TASK-113 可在 `backend/tests/fakes` 扩展确定性状态模型，表示目录及父子关系、
  离线任务、递归文件、原画/HLS/小文件能力和删除状态，并提供只读查询用于 E2E 断言。
- REQ-CHG-142: 状态模型必须继续实现冻结 Cloud115Port；现有返回脚本和脱敏调用记录保持兼容，
  故障注入只接受稳定 `Cloud115Problem`，不得保存完整磁力、Cookie 或能力 URL到可打印状态。
- REQ-CHG-143: Fake 的时间和状态推进必须由测试显式控制，不使用真实 60 秒等待、后台线程、网络
  或不确定 sleep；目录移动、账号变化、取消、离线完成、删除失败和 worker 恢复均可确定性重放。

**Acceptance Criteria**:

- [x] Fake 可查询任务目录、离线状态、文件归属与删除结果，既有 Fake 单元测试构造方式不回归。
- [x] Fake 的 repr、调用记录、pytest node ID 和失败输出不暴露完整秘密或能力 URL。

## MODIFIED

### TASK-113 验证范围

**Previous Behavior**: `ac-mapping` 覆盖 AC-013..017、AC-035/036、AC-079..122、AC-127..129
和 AC-132，并把“本工作流所有 `[IMP]` 有 Fake E2E 证据”作为 DoD，包含客户端菜单、seek、
本地字幕、UI 控件和交付平台行为。

**New Behavior**: 验证范围收窄为已交付后端可观察切片：AC-013..017、AC-035/036、
AC-079..102、AC-107..113、AC-115..122、AC-127..129，以及 AC-132 的 Phase 2 观察点。
客户端 UI、倒计时、自动播放决策、播放器控制、本地文件生命周期和真实链路继续由 TASK-201..213、
TASK-301..313 所有。TASK-113 不转移前序实现任务的 AC 所有权。

### 60 秒与自动播放证据

**Previous Behavior**: 后端 E2E 直接验证“60 秒退出后台继续”和“排队/后台完成不自动播放”。

**New Behavior**: 后端 E2E 使用可控时钟证明 60 秒经过不会改变 CacheJob 或产生 timer 事件；
`started/queued` disposition、queued 后续 started、后台 ready 通知与快照可恢复。ready 事务不得
创建 PlaybackSession。实际 60 秒退出、全屏阻断、通知展示和是否导航播放器由客户端任务验证。

### AC-132 观察点

**Previous Behavior**: TASK-014 已证明元数据/AI/GFriends 故障不影响目录和排行榜，TASK-113
又笼统要求重复相同结论。

**New Behavior**: TASK-113 复用同类固定故障事实，在同一已入库影片上额外证明 115 缓存播放、
字幕、进度和清理链路仍可用；不重复 TASK-014 的全量元数据 E2E 或 provider 实现测试。

### 任务分类与 DoR

**Previous Behavior**: `cross-boundary: false`，DoR 要求 Fake 已支持所有状态。

**New Behavior**: TASK-113 是跨边界 E2E 聚合，标记为 `cross-boundary: true`。DoR 只要求前序任务
completed、Cloud115Port/脚本 Fake 可用及隔离 PostgreSQL runner 可用；状态化 Fake 是本任务测试
基础设施交付物，不再作为循环前置条件。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-113 / Phase 2 E2E scope | MODIFIED | MEDIUM |
| backend Cloud115 E2E contract | ADDED | MEDIUM |
| test-only Fake115 state model | ADDED | MEDIUM |
| product API / Schema / runtime config | UNCHANGED | LOW |

## Testing Strategy

- 自包含测试覆盖 Fake 状态模型、故障注入兼容性、脱敏 repr 和既有脚本 API 回归。
- PostgreSQL E2E 覆盖主链、2/10 disposition 与恢复观察面、安全清理、播放安全和 AC-132。
- Fast 运行最大合理自包含集合、格式/lint/类型和完整差异检查；Final 由唯一 Compose runner 收集
  全部 integration/E2E 并验证真实进程、迁移、健康、重启、ready 降级和资源清理。
- 默认套件不访问真实 115；TASK-213 继续拥有 AC-130 发布门禁。

## Rollback Plan

提交前可整体回退本变更、E2E 契约、测试 Fake 和 E2E 文件，不影响生产数据。提交后若需要调整
证据范围，必须以前向变更同步 TASK-113、任务索引、追踪矩阵和契约，不得只删除测试。

## Task Impact

不新增或拆分任务。TASK-113 在同一中文提交中同步本变更、E2E 契约、任务文件、任务索引、
追踪矩阵、测试和交接；TASK-114 仍是后续代码清理任务。
