---
id: TASK-107
title: "TTL、LRU、租约与安全清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-103, TASK-105]
ac-mapping: [AC-094, AC-095, AC-096, AC-097, AC-098]
imp-requirements: [REQ-018]
cross-boundary: false
external-dependency-risk: true
provides: [sliding TTL, ready LRU, minimal playback session schema, playback lease, ownership verifier, cleanup worker]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-107: TTL、LRU、租约与安全清理

**功能描述**: 实现 24 小时可配置滑动 TTL、默认 20 就绪上限、播放租约、运行任务排除和证明式 115 安全清理。

**规格映射**: AC-094 至 AC-098

## 外部依赖风险

- **依赖**: 115 directory_info/delete。
- **状态**: 用户可能手动移动/删除目录，删除请求可能失败或结果不确定。
- **缓解**: 每次清理重新证明账号/root/task/parent/owner，明确 not-found 才视为已清理。
- **冻结边界**: [TASK-107 缓存生命周期确定性边界](../changes/2026-07-28--task-107-cache-lifecycle-determinism.md)。

## 验收条件

- [x] ready 缓存默认 24 小时滑动 TTL，管理员可设 1 至 168 小时；对应 AC-094。
- [x] ready capacity 默认安全收敛到 20，按稳定 last_accessed_at LRU 清理且失败不虚减容量；对应 AC-095。
- [x] 有效播放租约阻止清理，running 任务不参与 TTL/LRU 且只能取消；对应 AC-096、AC-097。
- [x] 只有确认远端删除成功/明确不存在才 cleaned，失败可观察和重试且不释放容量；归属不符 detached；对应 AC-098。

## Definition of Ready

- [x] TASK-103 状态分组、TASK-105 task_dir/media 定位可用。
- [x] binding account/root 与 job snapshot 可供归属验证。
- [x] 服务器时间是 TTL 唯一时钟来源。

## 技术上下文

- TTL/LRU 候选是 `awaiting_selection/ready`；查询排除 lease、running、cleaning，并锁住被选 job。
- 20 是删除确认后的收敛目标；cleanup_failed/cleaning 继续占 ready capacity。
- 本任务创建最小 playback_session Schema 和完整 playback_lease Schema/服务，不提前实现 TASK-108 API。
- lease 获取/续期与 CacheJob 行锁、当前 TTL 设置和访问窗口刷新处于同一事务。
- 目录 parent 不符进入 detached，不追踪新位置删除。
- cleanup_failed 仍计入 ready capacity，手动 retry 复用同一清理器。
- TASK-104 只确认远端离线取消并把仍有任务目录的 job 交到 `cleaning`；本任务独占目录归属
  证明、远端删除和 `cleaned/cleanup_failed/detached` 终结。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/ttl_lru.py` - 滑动 TTL/LRU 选择。
- `backend/src/sakuraplayer/playback/lease.py` - 播放租约 repository/服务。
- `backend/src/sakuraplayer/playback/models.py` - 最小播放会话和租约模型。
- `backend/src/sakuraplayer/cloud_cache/ownership.py` - 受管目录证明。
- `backend/src/sakuraplayer/cloud_cache/cleanup.py` - 幂等远端删除和重试。
- `backend/tests/unit/cloud_cache/test_ttl_lru.py` - 时间/容量/租约。
- `backend/tests/integration/cloud_cache/test_safe_cleanup.py` - 移动/删除/失败故障注入。

## 测试说明

**单元测试**:

- 1/24/168 小时边界、访问刷新、20 上限、同时间稳定 LRU、lease 排除。
- running/cancelling/cleanup_failed 状态的容量和清理资格。
- 最小 session/lease 外键、单 session/client 唯一与有效租约定义。

**集成测试**:

- 正常删除、目录已不存在、被移到根外、root 改变、账号重绑、删除超时和重试。
- 有租约时手动/自动清理均拒绝，租约结束后可清理。

**边界条件**:

- 清理与心跳竞态、两个 worker 争抢、进程在删除后/提交前崩溃。

## Definition of Done

- [x] TTL/LRU/lease/ownership/cleanup 完成。
- [x] 不会删除 `SakuraPlayer-Cache` 外内容。
- [x] 清理失败不虚减容量。

## 完成证据

- Focused 最终相关回归 25 项通过；Fast 为 694 passed、8 deselected，全仓 Ruff
  format/lint、7 个任务生产模块 mypy、宿主 Docker 配置和完整差异检查通过。
- 滑动 TTL、稳定 LRU、cleaning 预计释放量、lease/cleanup 锁顺序、claim/attempt fencing、
  目录归属证明、崩溃恢复和敏感信息边界审计收敛，无剩余 P0/P1/P2。
- Compose Final 第四次尝试通过：自包含 694 passed、8 deselected，PostgreSQL
  integration/E2E 103 passed、15 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启
  持久性、ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。

**依赖**: TASK-103, TASK-105

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-107.md"`
