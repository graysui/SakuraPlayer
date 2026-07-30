---
id: TASK-205
title: "日周月 TOP250 排行榜"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-204]
ac-mapping: [AC-046, AC-069, AC-070, AC-071, AC-072, AC-073]
imp-requirements: [REQ-009, REQ-014]
cross-boundary: false
external-dependency-risk: false
provides: [Windows rankings page]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-205: 日周月 TOP250 排行榜

**功能描述**: 实现基于后端本地快照的日榜、周榜、月榜、TOP250 和适用年份筛选桌面页面。

**规格映射**: AC-046、AC-069 至 AC-073

## 验收条件

- [ ] 页面只调用本地快照 API，不在打开时直接访问 JavDB；对应 AC-069。
- [ ] 提供日/周/月/TOP250 Tab 或分段选择，年份只在适用榜单显示；对应 AC-070。
- [ ] 页面只显示后端返回的有 AVdb 来源且 core_ready 影片；对应 AC-071。
- [ ] 缺元数据由后端排队，客户端保留快照/补全状态，失败不清空现有榜单；对应 AC-072、AC-073。
- [ ] TOP250 从未有快照且凭据未配置时显示可操作的不可用状态，不影响其他榜单；对应 AC-046。

## Definition of Ready

- [ ] TASK-204 Shell、MovieCard/影片摘要 DTO 和 TASK-012 `/rankings` 可用。
- [ ] TASK-205 自身拥有榜单/年份/游标 DTO/API；错误 details、选择、分页、失败恢复与布局已由 [Windows 排行榜客户端契约](../contracts/windows-rankings-client.md) 确定。
- [ ] 榜单卡复用 MovieCard 的可读子集并保留原始 rank。

## 技术上下文

- synced_at 是本地快照时间；页面刷新只重新请求后端。
- 切换 board/year 重置游标和滚动，返回页面可保留本机选择。
- 迟到响应不得覆盖新选择；刷新/追加失败保留当前成功快照，认证会话变化清空全部状态。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/rankings/data/rankings_api.dart` - 快照 DTO/API。
- `windows/lib/features/rankings/presentation/rankings_controller.dart` - board/year/分页。
- `windows/lib/features/rankings/presentation/rankings_page.dart` - 桌面榜单布局。
- `windows/test/features/rankings/rankings_controller_test.dart` - 选择和保留。
- `windows/test/features/rankings/rankings_page_test.dart` - 年份/排名/错误态。

## 测试说明

- 日/周/月不显示无效年份，TOP250 只发送选择的适用年份。
- 保留 rank 间隙、synced_at、真实空态、`ranking_snapshot_unavailable` 和追加失败已有卡片。
- 断网/同步失败时客户端不清空当前成功 snapshot。

## Definition of Done

- [ ] 四榜单、年份、分页和快照错误态完成。
- [ ] 页面无 JavDB 直接网络依赖。
- [ ] 测试通过。

**依赖**: TASK-204

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-205.md"`
