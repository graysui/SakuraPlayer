---
id: TASK-009
title: "演员映射与 GFriends"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-008]
ac-mapping: [AC-049, AC-050, AC-051, AC-052, AC-053]
imp-requirements: [REQ-010]
cross-boundary: false
external-dependency-risk: true
provides: [actor mapping snapshot, authoritative aliases, GFriends unique asset index]
---

# TASK-009: 演员映射与 GFriends

**功能描述**: 每周刷新演员映射 XML 和 GFriends 索引，保存权威别名并只接受唯一明确的写真/头像匹配。

**规格映射**: AC-049 至 AC-053

## 外部依赖风险

- **依赖**: 指定 GitHub Raw actor-mapping.xml、Filetree.json 和 Content 基址。
- **状态**: 地址与真实 318,928 映射已核验，上游仍可能不可用或改变。
- **缓解**: SHA-256 快照、最近成功缓存、XXE 禁用、唯一匹配和固定歧义 fixture。

## 验收条件

- [ ] 两个索引每周刷新，失败继续使用最近成功快照；对应 AC-049。
- [ ] 保存中日文名、权威别名和可用简介，用户搜索词不进入别名；对应 AC-050。
- [ ] GFriends 头像/写真只有唯一姓名或别名匹配才关联，歧义丢弃；对应 AC-051。
- [ ] 只持久化索引和 URL，不全量镜像图片，并区分永久目录图片与客户端临时 GFriends 图片；对应 AC-052、AC-053。

## Definition of Ready

- [ ] TASK-008 Actor 稳定 JavDB ID 和永久图片模型可用。
- [ ] XML/JSON 主机白名单及每周调度入口已确认。
- [ ] 同名多人歧义 fixture 已准备。

## 技术上下文

- XML 解析禁用 DTD、外部实体和网络。
- `normalized_alias -> actor_ids` 是多值索引，只有集合大小 1 才匹配。
- GFriends URL 由客户端按需缓存，后端不下载 Content 全集。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/actor_mapping.py` - XML 快照和权威别名。
- `backend/src/sakuraplayer/catalog/gfriends.py` - Filetree 索引与唯一匹配。
- `backend/src/sakuraplayer/scheduler/provider_snapshots.py` - 每周刷新任务。
- `backend/tests/fixtures/catalog/actor_mapping.xml` - 正常/XXE/歧义样本。
- `backend/tests/fixtures/catalog/gfriends.json` - URL 和同名样本。
- `backend/tests/integration/catalog/test_actor_assets.py` - 快照回退和生命周期。

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

- [ ] 演员映射、周更、唯一匹配和 URL 索引完成。
- [ ] XXE 与歧义测试通过。
- [ ] 永久/临时图片生命周期无混用。

**依赖**: TASK-008

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-009.md"`
