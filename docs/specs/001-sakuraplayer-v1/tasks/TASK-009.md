---
id: TASK-009
title: "演员映射与 GFriends"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-008]
ac-mapping: [AC-049, AC-050, AC-051, AC-052, AC-053]
imp-requirements: [REQ-010]
cross-boundary: false
external-dependency-risk: true
provides: [actor mapping snapshot, authoritative aliases, GFriends unique asset index]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-009: 演员映射与 GFriends

**功能描述**: 每周刷新演员映射 XML 和 GFriends 索引，保存权威别名并只接受唯一明确的写真/头像匹配。

**规格映射**: AC-049 至 AC-053

## 外部依赖风险

- **依赖**: 指定 GitHub Raw actor-mapping.xml、Filetree.json 和 Content 基址。
- **状态**: 地址与真实 318,928 映射已核验，上游仍可能不可用或改变。
- **缓解**: SHA-256 快照、最近成功缓存、XXE 禁用、唯一匹配和固定歧义 fixture。

## 验收条件

- [x] 两个索引每周刷新，失败继续使用最近成功快照；对应 AC-049。
- [x] 保存中日文名、权威别名和可用简介，用户搜索词不进入别名；对应 AC-050。
- [x] GFriends 头像/写真只有唯一姓名或别名匹配才关联，歧义丢弃；对应 AC-051。
- [x] 只持久化索引和 URL，不全量镜像图片，并区分永久目录图片与客户端临时 GFriends 图片；对应 AC-052、AC-053。

## Definition of Ready

- [x] TASK-008 Actor 稳定 JavDB ID 和永久图片模型可用。
- [x] XML/JSON 主机白名单及每周调度入口已由 [TASK-009 提供方快照安全与重建边界](../changes/2026-07-26--task-009-provider-snapshot-boundaries.md) 冻结。
- [x] 正常、XXE 与同名多人歧义 fixture 已准备。

## 技术上下文

- XML 解析禁用 DTD、外部实体和网络。
- `normalized_alias -> actor_ids` 是多值索引，只有集合大小 1 才匹配。
- GFriends URL 由客户端按需缓存，后端不下载 Content 全集。

## 实施批次

| 批次 | 行为闭环 | 聚焦证据 |
|---|---|---|
| 1 | provider snapshot request、两类 current 快照和 GFriends asset Schema | 0009 迁移、约束、重复 slot、claim/lease 和 current 唯一 |
| 2 | 精确 URL 安全下载、defusedxml/XML 与 Filetree 解析、原子文件激活 | 重定向、16/32 MiB、XXE、非法结构/路径、摘要和最近成功回退 |
| 3 | Actor Mapping 唯一身份关联、mapping 别名协调和 GFriends 全量资产重建 | 0/1/多匹配、JavDB 别名保护、删除、跨演员重复 URL 和 profile/gallery |
| 4 | worker consumer、周日 05:00 scheduler 与 metadata stage 接线 | 持久入队、默认无真实网络、线程错误传播和无快照 warning |
| 5 | Fast、只读审计、Final、任务与交接同步 | 完整门禁证据和一次中文提交 |

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/actor_mapping.py` - XML 快照和权威别名。
- `backend/src/sakuraplayer/catalog/gfriends.py` - Filetree 索引与唯一匹配。
- `backend/src/sakuraplayer/catalog/provider_snapshots.py` - 安全下载、快照激活与持久请求队列。
- `backend/src/sakuraplayer/scheduler/provider_snapshots.py` - 每周刷新任务。
- `backend/src/sakuraplayer/worker/provider_snapshots.py` - worker claim 与刷新 consumer。
- `backend/alembic/versions/0009_provider_snapshots.py` - 快照请求、current 快照和 GFriends URL 索引。
- `backend/tests/fixtures/catalog/actor_mapping.xml` - 正常/XXE/歧义样本。
- `backend/tests/fixtures/catalog/actor_mapping_xxe.xml` - DTD 与外部实体拒绝样本。
- `backend/tests/fixtures/catalog/gfriends.json` - URL 和同名样本。
- `backend/tests/start/test_provider_snapshot_migration.py` - Schema 与约束。
- `backend/tests/unit/catalog/test_actor_mapping.py` - XML、唯一 Actor 和别名协调。
- `backend/tests/unit/catalog/test_gfriends.py` - Filetree 安全与唯一 URL 资产。
- `backend/tests/unit/catalog/test_provider_snapshot_service.py` - 下载、激活、回退和队列。
- `backend/tests/integration/catalog/test_actor_assets.py` - 快照回退和生命周期。

**修改**:

- `backend/src/sakuraplayer/catalog/models.py` - 快照请求、snapshot 与 GFriends asset 模型。
- `backend/src/sakuraplayer/catalog/providers/runtime.py` - `actor_map/gfriends` stage 接线。
- `backend/src/sakuraplayer/scheduler/__main__.py` - 持久入队和固定周更注册。
- `backend/src/sakuraplayer/worker/__main__.py` - snapshot consumer 生命周期。
- `backend/pyproject.toml` - 固定 defusedxml 0.7.1。

## 测试说明

**单元测试**:

- 验证权威别名合并、casefold 去重、搜索词不写入、XXE 样本拒绝。
- 验证 0/1/多个演员匹配时只有 1 个结果关联 URL。

**集成测试**:

- 周更成功后上游失败，验证最近快照继续服务。
- 验证数据库只有索引/URL，永久图片卷没有 GFriends 全量资产。

**边界条件**:

- 空快照、相同 URL 多映射、中文/日文同名、部分下载失败。

## Definition of Done

- [x] 演员映射、周更、唯一匹配和 URL 索引完成。
- [x] XXE 与歧义测试通过。
- [x] 永久/临时图片生命周期无混用。

## 验证证据

- Focused/Fast：TASK-009 Schema、快照队列/下载、Actor Mapping、GFriends、worker、scheduler 与 runtime 聚焦组合 60 passed；自包含 342 passed、7 deselected；PostgreSQL 生命周期与 Schema 聚焦 5 passed；只读 compileall、宿主 Docker 配置和 `git diff --check` 通过。
- 只读审计：完整差异复审修复了 JavDB 日文名所有权、GFriends scheme 路径校验、快照 size 约束和 PostgreSQL 并发证据缺口，最终无剩余 P0/P1/P2；默认测试仅使用 fixture 与 MockTransport。
- Final：`backend/tests/run-compose.ps1` 尝试 1 通过；自包含 342 passed、7 deselected，PostgreSQL/Compose 71 passed、12 deselected，并完成迁移、五服务健康、认证 canary、敏感日志扫描、重启持久性、ready 降级恢复和隔离资源清理；未访问真实 GitHub Raw 或 GFriends Content。

**依赖**: TASK-008

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-009.md"`
