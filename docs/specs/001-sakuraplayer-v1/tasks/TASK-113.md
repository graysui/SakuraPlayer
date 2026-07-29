---
id: TASK-113
title: "115 缓存播放后端端到端测试"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-101, TASK-102, TASK-103, TASK-104, TASK-105, TASK-106, TASK-107, TASK-108, TASK-109, TASK-110, TASK-111, TASK-112]
ac-mapping: [AC-013..AC-017, AC-035, AC-036, AC-079..AC-102, AC-107..AC-113, AC-115..AC-122, AC-127..AC-129, AC-132]
imp-requirements: [REQ-004, REQ-007, REQ-016..REQ-024]
cross-boundary: true
external-dependency-risk: true
provides: [cloud115 cache playback fake e2e suite]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-113: 115 缓存播放后端端到端测试

**功能描述**: 用状态化 Fake 115、真实 PostgreSQL 和生产服务组合验证扫码、点击来源、容量 disposition、解析、播放、字幕、进度、TTL/LRU、安全清理和恢复的后端可观察闭环。

**规格映射**: TASK-101 至 TASK-112 已交付的后端切片，以及 AC-132 `[SEF]` 的 Phase 2 观察点；逐项 `[IMP]` 证据仍由前序任务门禁所有

**E2E 边界**: [115 缓存播放后端 E2E 契约](../contracts/backend-cloud115-e2e.md)

## 验收条件

- [x] 完成扫码 -> 专属根 -> 用户点击来源 -> 离线 -> 文件选择 -> ready -> 原画/HLS -> 字幕 -> 进度 -> 清理主流程。
- [x] 验证 2 运行/10 排队、`started/queued` disposition、可控时钟经过 60 秒不写 timer 状态/事件、排队后开始和后台完成可由事件/通知/快照恢复；ready 事务不创建播放会话。
- [x] 目录移动、账号变化、活跃租约、清理失败均不会误删根外内容或虚减容量。
- [x] 单个外部元数据/AI/GFriends 故障不使已入库目录、榜单或 115 播放整体不可用；对应 `[SEF]` AC-132。

## Definition of Ready

- [x] TASK-101 至 TASK-112 均为 `completed` 且已有各自中文提交。
- [x] 冻结 Cloud115Port、现有脚本 Fake 和稳定故障注入边界可用；状态化远端模型由本任务交付。
- [x] 现有 E2E/Final runner 可从真实 Alembic head 创建隔离 PostgreSQL 数据库。

## 技术上下文

- 这是后端发布给 Windows 的契约门禁，不访问真实 115。
- 每个关键转换至少断言数据库与一个公开观察面；涉及远端副作用时同时断言 Fake 115 状态。
- 60 秒客户端倒计时、全屏等待、自动播放决策、播放器菜单/seek/控件和本地字幕文件生命周期由客户端任务验证。
- E2E 不新增产品行为，补充验证不得作为阻断要求。

## 实现文件（仅文件名）

**创建**:

- `backend/tests/fakes/cloud115_state.py` - 可查询远端状态与确定性推进。
- `backend/tests/e2e/test_cloud115_cache_playback_e2e.py` - 主链路。
- `backend/tests/e2e/test_cache_capacity_wait_e2e.py` - 2/10/60 秒/通知。
- `backend/tests/e2e/test_cache_cleanup_faults_e2e.py` - 租约/移动/删除/恢复。
- `backend/tests/e2e/test_playback_security_e2e.py` - 签名/UA/302/字幕/秘密扫描。

**修改**:

- `backend/tests/e2e/conftest.py` - 组合缓存/播放生产服务与 worker pipeline。

## 测试说明

**E2E 主流程**:

- 单文件、多个候选、连续分段三种资源；原画成功、原画失败回退、用户兼容模式。
- 两个后端 client_instance 身份交替写影片级进度，验证 CAS、影片级共享事实和 TTL；不声明客户端 UI 已实现。

**故障流程**:

- Cookie expired/unavailable、提交超时已受理、违规拒绝、目录移动、清理失败、worker 崩溃。
- 日志和数据库扫描无 Cookie、磁力、短链、字幕正文。

## Definition of Done

- [x] 映射 AC 的后端可观察切片有代表性 Fake E2E 证据，前序任务逐项证据保持绿色。
- [x] AC-132 故障隔离观察点通过。
- [x] 测试无真实账号/付费访问且报告、日志、数据库和 Fake 可打印状态无秘密。
- [x] Final runner 执行全部 E2E，完整 Compose、重启、降级恢复和资源清理通过。
- [x] Windows 可以只依赖冻结契约开始完整联调。

## 完成证据

- 状态 Fake 与 TASK-113 Focused 聚合集 15 passed；状态化远端、脱敏、主链、容量、清理故障、
  播放安全、提交不确定恢复、来源拒绝和 AC-132 均通过。
- Fast 自包含 776 passed、8 deselected；cloud_cache/playback PostgreSQL 集成与 TASK-113 E2E
  38 passed；Ruff format/lint、52 个生产文件 mypy、宿主 Docker 配置、完整差异与只读审计通过，
  无剩余 P0/P1/P2。
- Compose Final 首次尝试通过：自包含 776 passed、8 deselected，PostgreSQL integration/E2E
  125 passed、16 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启、ready 降级恢复和
  隔离资源清理全部完成，默认测试未访问真实 115、JavDB 写操作或付费 AI。

**完成日期**: 2026-07-29

**依赖**: TASK-101..TASK-112

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-113.md"`
