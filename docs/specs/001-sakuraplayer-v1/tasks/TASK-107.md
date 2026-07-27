---
id: TASK-107
title: "TTL、LRU、租约与安全清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-103, TASK-105]
ac-mapping: [AC-094, AC-095, AC-096, AC-097, AC-098]
imp-requirements: [REQ-018]
cross-boundary: false
external-dependency-risk: true
provides: [sliding TTL, ready LRU, playback lease, ownership verifier, cleanup worker]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-107: TTL、LRU、租约与安全清理

**功能描述**: 实现 24 小时可配置滑动 TTL、默认 20 就绪上限、播放租约、运行任务排除和证明式 115 安全清理。

**规格映射**: AC-094 至 AC-098

## 外部依赖风险

- **依赖**: 115 directory_info/delete。
- **状态**: 用户可能手动移动/删除目录，删除请求可能失败或结果不确定。
- **缓解**: 每次清理重新证明账号/root/task/parent/owner，明确 not-found 才视为已清理。

## 验收条件

- [ ] ready 缓存默认 24 小时滑动 TTL，管理员可设 1 至 168 小时；对应 AC-094。
- [ ] 默认最多 20 个 ready，按 last_accessed_at 清理最久未访问；对应 AC-095。
- [ ] 有效播放租约阻止清理，running 任务不参与 TTL/LRU 且只能取消；对应 AC-096、AC-097。
- [ ] 只有确认远端删除成功/明确不存在才 cleaned，失败可观察和重试且不释放容量；对应 AC-098。

## Definition of Ready

- [ ] TASK-103 状态分组、TASK-105 task_dir/media 定位可用。
- [ ] binding account/root 与 job snapshot 可供归属验证。
- [ ] 服务器时间是 TTL 唯一时钟来源。

## 技术上下文

- LRU 查询排除 lease、running、cleaning，并锁住被选 job。
- 目录 parent 不符进入 detached，不追踪新位置删除。
- cleanup_failed 仍计入 ready capacity，手动 retry 复用同一清理器。
- TASK-104 只确认远端离线取消并把仍有任务目录的 job 交到 `cleaning`；本任务独占目录归属
  证明、远端删除和 `cleaned/cleanup_failed/detached` 终结。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/ttl_lru.py` - 滑动 TTL/LRU 选择。
- `backend/src/sakuraplayer/playback/lease.py` - 播放租约 repository/服务。
- `backend/src/sakuraplayer/cloud_cache/ownership.py` - 受管目录证明。
- `backend/src/sakuraplayer/cloud_cache/cleanup.py` - 幂等远端删除和重试。
- `backend/tests/unit/cloud_cache/test_ttl_lru.py` - 时间/容量/租约。
- `backend/tests/integration/cloud_cache/test_safe_cleanup.py` - 移动/删除/失败故障注入。

## 测试说明

**单元测试**:

- 1/24/168 小时边界、访问刷新、20 上限、同时间稳定 LRU、lease 排除。
- running/cancelling/cleanup_failed 状态的容量和清理资格。

**集成测试**:

- 正常删除、目录已不存在、被移到根外、root 改变、账号重绑、删除超时和重试。
- 有租约时手动/自动清理均拒绝，租约结束后可清理。

**边界条件**:

- 清理与心跳竞态、两个 worker 争抢、进程在删除后/提交前崩溃。

## Definition of Done

- [ ] TTL/LRU/lease/ownership/cleanup 完成。
- [ ] 不会删除 `SakuraPlayer-Cache` 外内容。
- [ ] 清理失败不虚减容量。

**依赖**: TASK-103, TASK-105

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-107.md"`
