---
id: TASK-306
title: "HarmonyOS 女优列表详情与写真"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
completed-at: 2026-08-05
dependencies: [TASK-303]
ac-mapping: [AC-051, AC-052, AC-053, AC-075, AC-076, AC-077]
imp-requirements: [REQ-010, REQ-015]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS actress listing detail gallery cache]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-306: HarmonyOS 女优列表详情与写真

**功能描述**: 实现姓名/别名搜索、女优详情、单一收藏、关联影片和 GFriends 写真私有有界缓存。

**规格映射**: AC-051 至 AC-053、AC-075 至 AC-077

## 外部依赖风险

- **依赖**: 后端已唯一匹配的 GFriends HTTPS URL。
- **状态**: 图片可失败或占用较多内存。
- **缓解**: 只信任后端 URL、cacheDir LRU、ImageSource 按需解码、onMemoryLevel 清理。

## 验收条件

- [x] 列表支持姓名/权威别名搜索；对应 AC-075。
- [x] 详情显示头像、中日文名、别名、简介、写真、关联影片和收藏；对应 AC-076。
- [x] 女优列表可用 `favorite=true` 分页查看单一收藏集合，无自定义播放列表；对应 AC-077。
- [x] GFriends 只缓存后端唯一匹配 URL，临时图库与永久目录图片生命周期分开；对应 AC-051 至 AC-053。

## Definition of Ready

- [x] TASK-303 Search/Navigation 和 Actor API 可用。
- [x] Core File Kit cacheDir、内存回调和 Image Kit 签名已核验。
- [x] 不在客户端按名字重新匹配。

## 技术上下文

- WaterFlow/Grid 长列表使用稳定 actor/asset ID key。
- 组件离屏释放高分辨率 PixelMap；系统低内存时缩减缓存。
- listener 在 aboutToDisappear 注销。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/actors/ActorsStore.ets` - 搜索/分页/收藏。
- `harmony/entry/src/main/ets/features/actors/ActorsPage.ets` - 女优网格。
- `harmony/entry/src/main/ets/features/actors/ActorDetailPage.ets` - 资料/写真/影片。
- `harmony/entry/src/main/ets/core/images/GfriendsCache.ets` - 文件/内存 LRU。
- `harmony/entry/src/ohosTest/ets/test/Actors.test.ets` - 搜索/详情/收藏。
- `harmony/entry/src/ohosTest/ets/test/GfriendsCache.test.ets` - 缓存/内存回收。

## 测试说明

- 姓名/别名、无头像/简介/写真、收藏和关联影片导航（Actors JsUnit 12 项 + UiTest 2 项）。
- URL 失败/重复/过期、低内存清理、退出后 listener 注销（GfriendsCache JsUnit 14 项）。
- 临时写真删除不影响目录封面显示（文件条目级 LRU 与头像独立）。

## Definition of Done

- [x] 女优列表/详情/收藏/写真完成。
- [x] 有界缓存和内存回收有测试。
- [x] 客户端无歧义匹配逻辑。

**实现证据**: `ActorsStore.ets`（300ms 防抖/favorite 模式/generation/收藏在途防重与 scope 隔离）、
`ActorDetailStore.ets`（收藏双向同步 + pendingFavorite 合并）、`ActorsPage.ets`/`ActorDetailPage.ets`
（搜索/详情/写真/关联影片/收藏）、`GfriendsCache.ets`（URL 白名单逐字段 + 编码形态拒绝、匿名下载
3 重定向逐跳/8MiB/签名+Content-Type、文件 LRU 512/256MiB/7 天、内存 PixelMap LRU 64 张、
onMemoryLevel 收缩、证明式清理）；ohosTest 模拟器实测 **93/93 全绿**，debug/release HAP 构建且
`verify-app success`（API 24 Release、INTERNET 最小权限）。

**依赖**: TASK-303

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-306.md"`
