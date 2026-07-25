---
id: TASK-305
title: "HarmonyOS 日周月 TOP250 排行榜"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-303]
ac-mapping: [AC-046, AC-069, AC-070, AC-071, AC-072, AC-073]
imp-requirements: [REQ-009, REQ-014]
cross-boundary: false
external-dependency-risk: false
provides: [HarmonyOS rankings page]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-305: HarmonyOS 日周月 TOP250 排行榜

**功能描述**: 实现移动友好的四类榜单、年份筛选、本地快照时间、下拉刷新和游标加载。

**规格映射**: AC-046、AC-069 至 AC-073

## 验收条件

- [ ] 页面只读后端本地快照；对应 AC-069。
- [ ] 日/周/月/TOP250 与适用年份筛选可用；对应 AC-070。
- [ ] 只显示有来源且 core_ready 影片；对应 AC-071。
- [ ] 缺元数据/同步失败时保留已有快照并显示安全状态；对应 AC-072、AC-073。
- [ ] TOP250 从未有快照且凭据未配置时显示可操作的不可用状态，不影响其他榜单；对应 AC-046。

## Definition of Ready

- [ ] TASK-303 Navigation 和 Ranking DTO/API 可用。
- [ ] 年份只在后端声明适用时显示。
- [ ] 排名卡复用 MovieCard，不复制目录业务逻辑。

## 技术上下文

- 用 Tabs/segmented-style 系统组件表达四榜单，年份使用 Select。
- Refresh 只调用后端快照 API，不触发客户端 JavDB 抓取。

## 实现文件（仅文件名）

**创建**:

- `harmony/entry/src/main/ets/features/rankings/RankingsStore.ets` - board/year/游标。
- `harmony/entry/src/main/ets/features/rankings/RankingsPage.ets` - 榜单/年份/刷新。
- `harmony/entry/src/ohosTest/ets/test/RankingsStore.test.ets` - 参数/快照保留。
- `harmony/entry/src/ohosTest/ets/test/RankingsPage.test.ets` - UiTest 榜单切换。

## 测试说明

- 四榜单、年份可见性、rank 间隙、synced_at 和分页。
- 下拉刷新失败保留当前列表；区分真实空态和 `ranking_snapshot_unavailable`；raw-only 不显示但后端可排队。
- 直屏/横屏和长标题无重叠。

## Definition of Done

- [ ] 四榜单、年份、刷新和错误态完成。
- [ ] 无 JavDB 客户端直接访问。
- [ ] Hypium/UiTest 通过。

**依赖**: TASK-303

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-305.md"`
