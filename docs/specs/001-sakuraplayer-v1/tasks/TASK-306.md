---
id: TASK-306
title: "HarmonyOS 女优列表详情与写真"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-303]
ac-mapping: [AC-051, AC-052, AC-053, AC-075, AC-076, AC-077]
imp-requirements: [REQ-010, REQ-015]
cross-boundary: false
external-dependency-risk: true
provides: [HarmonyOS actress listing detail gallery cache]
---

# TASK-306: HarmonyOS 女优列表详情与写真

**功能描述**: 实现姓名/别名搜索、女优详情、单一收藏、关联影片和 GFriends 写真私有有界缓存。

**规格映射**: AC-051 至 AC-053、AC-075 至 AC-077

## 外部依赖风险

- **依赖**: 后端已唯一匹配的 GFriends HTTPS URL。
- **状态**: 图片可失败或占用较多内存。
- **缓解**: 只信任后端 URL、cacheDir LRU、ImageSource 按需解码、onMemoryLevel 清理。

## 验收条件

- [ ] 列表支持姓名/权威别名搜索；对应 AC-075。
- [ ] 详情显示头像、中日文名、别名、简介、写真、关联影片和收藏；对应 AC-076。
- [ ] 女优列表可用 `favorite=true` 分页查看单一收藏集合，无自定义播放列表；对应 AC-077。
- [ ] GFriends 只缓存后端唯一匹配 URL，临时图库与永久目录图片生命周期分开；对应 AC-051 至 AC-053。

## Definition of Ready

- [ ] TASK-303 Search/Navigation 和 Actor API 可用。
- [ ] Core File Kit cacheDir、内存回调和 Image Kit 签名已核验。
- [ ] 不在客户端按名字重新匹配。

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

- 姓名/别名、无头像/简介/写真、收藏和关联影片导航。
- URL 失败/重复/过期、低内存清理、退出后 listener 注销。
- 临时写真删除不影响目录封面显示。

## Definition of Done

- [ ] 女优列表/详情/收藏/写真完成。
- [ ] 有界缓存和内存回收有测试。
- [ ] 客户端无歧义匹配逻辑。

**依赖**: TASK-303

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-306.md"`
