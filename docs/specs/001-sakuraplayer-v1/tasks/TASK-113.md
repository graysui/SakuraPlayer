---
id: TASK-113
title: "115 缓存播放后端端到端测试"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-101, TASK-102, TASK-103, TASK-104, TASK-105, TASK-106, TASK-107, TASK-108, TASK-109, TASK-110, TASK-111, TASK-112]
ac-mapping: [AC-013..AC-017, AC-035, AC-036, AC-079..AC-122, AC-127..AC-129, AC-132]
imp-requirements: [REQ-004, REQ-007, REQ-016..REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [cloud115 cache playback fake e2e suite]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-113: 115 缓存播放后端端到端测试

**功能描述**: 用 Fake 115 和真实 PostgreSQL 验证扫码、点击来源、2/10、60 秒、解析、播放、字幕、进度、TTL/LRU、安全清理和恢复全链路。

**规格映射**: 本工作流所有 `[IMP]` 与 AC-132 `[SEF]`

## 验收条件

- [ ] 完成扫码 -> 专属根 -> 用户点击来源 -> 离线 -> 文件选择 -> ready -> 原画/HLS -> 字幕 -> 进度 -> 清理主流程。
- [ ] 同时验证 2 运行/10 排队、60 秒退出后台继续、排队/后台完成不自动播放。
- [ ] 目录移动、账号变化、活跃租约、清理失败均不会误删根外内容或虚减容量。
- [ ] 单个外部元数据/AI/GFriends 故障不使已入库目录、榜单或 115 播放整体不可用；对应 `[SEF]` AC-132。

## Definition of Ready

- [ ] TASK-101 至 TASK-112 已实现并评审。
- [ ] Fake 115 支持所有状态和故障注入。
- [ ] 测试数据库从真实 Alembic head 创建。

## 技术上下文

- 这是后端发布给 Windows 的契约门禁，不访问真实 115。
- 每个场景断言数据库、事件、API 和 Fake 115 远端状态四方一致。
- E2E 不新增产品行为，补充验证不得作为阻断要求。

## 实现文件（仅文件名）

**创建**:

- `backend/tests/e2e/test_cloud115_cache_playback_e2e.py` - 主链路。
- `backend/tests/e2e/test_cache_capacity_wait_e2e.py` - 2/10/60 秒/通知。
- `backend/tests/e2e/test_cache_cleanup_faults_e2e.py` - 租约/移动/删除/恢复。
- `backend/tests/e2e/test_playback_security_e2e.py` - 签名/UA/302/字幕/秘密扫描。

## 测试说明

**E2E 主流程**:

- 单文件、多个候选、连续分段三种资源；原画成功、原画失败回退、用户兼容模式。
- Windows/HarmonyOS 两 client_instance 交替心跳，验证影片级进度和 TTL。

**故障流程**:

- Cookie expired/unavailable、提交超时已受理、违规拒绝、目录移动、清理失败、worker 崩溃。
- 日志和数据库扫描无 Cookie、磁力、短链、字幕正文。

## Definition of Done

- [ ] 本工作流所有 `[IMP]` 有 Fake E2E 证据。
- [ ] AC-132 故障隔离观察点通过。
- [ ] Windows 可以只依赖冻结契约开始完整联调。

**依赖**: TASK-101..TASK-112

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-113.md"`
