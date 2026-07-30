---
id: TASK-206
title: "女优列表详情与写真"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-204]
ac-mapping: [AC-051, AC-052, AC-053, AC-075, AC-076, AC-077]
imp-requirements: [REQ-010, REQ-015]
cross-boundary: false
external-dependency-risk: true
provides: [Windows actress listing detail gallery cache]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-206: 女优列表详情与写真

**功能描述**: 实现女优姓名/别名搜索、列表、详情、单一收藏、关联影片和 GFriends 头像/写真按需客户端缓存。

**规格映射**: AC-051 至 AC-053、AC-075 至 AC-077

## 外部依赖风险

- **依赖**: 后端发布的 GFriends HTTPS URL。
- **状态**: 图片 URL 可失效，后端已完成唯一匹配。
- **缓解**: 客户端有界文件缓存、占位/重试，不再按姓名自行关联。

## 验收条件

- [ ] 列表按姓名和权威别名搜索；对应 AC-075。
- [ ] 详情显示头像、中日文名、别名、简介、写真、关联影片和收藏；对应 AC-076。
- [ ] 女优列表可用 `favorite=true` 分页查看单一收藏集合，不提供自定义列表；对应 AC-077。
- [ ] 客户端只缓存后端已唯一匹配的 GFriends URL，永久目录图片和 GFriends 临时缓存分开；对应 AC-051 至 AC-053。

## Definition of Ready

- [ ] TASK-204 Shell、MovieSummary/MovieCard、TASK-203 全局搜索和 `/actors` 契约可用。
- [ ] TASK-206 自身拥有 Actor DTO/API；本地 cacheDir、URL 安全、LRU/过期、并发、取消和占位资源已由 [Windows 女优客户端契约](../contracts/windows-actors-client.md) 确定。
- [ ] 客户端不做名字匹配或 URL 拼接。

## 技术上下文

- 写真使用实际图片网格/查看器，缓存位于应用私有 cacheDir。
- 大图按需加载并限制全局并发，同 URL 单飞；页面销毁取消无用请求，单图失败不清空成功详情。
- 全局搜索和列表进入女优详情；关联影片只读复用 MovieCard，影片详情导航归 TASK-207；收藏通过幂等 API。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/actors/data/actors_api.dart` - actor DTO/API。
- `windows/lib/features/actors/presentation/actors_controller.dart` - 搜索/分页/收藏。
- `windows/lib/features/actors/presentation/actors_page.dart` - 女优网格。
- `windows/lib/features/actors/presentation/actor_detail_page.dart` - 资料/写真/影片。
- `windows/lib/core/images/gfriends_cache.dart` - 有界临时图片缓存。
- `windows/test/features/actors/actor_pages_test.dart` - 搜索/详情/收藏。
- `windows/test/core/gfriends_cache_test.dart` - 缓存生命周期。

## 测试说明

- 姓名/别名搜索、长别名换行、无头像/简介/写真占位。
- 收藏幂等、全局搜索/列表到女优详情导航和关联影片卡片展示。
- GFriends URL 失败/重复/过期/退出清理，不影响永久封面缓存。

## Definition of Done

- [ ] 女优列表/详情/收藏/写真完成。
- [ ] 客户端无歧义姓名关联逻辑。
- [ ] 临时/永久图片缓存隔离测试通过。
- [ ] 下载 URL、8 MiB、四并发、取消、7 天期限及 512/256 MiB LRU 边界测试通过。

**依赖**: TASK-204

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-206.md"`
