---
id: TASK-221
title: "Windows 播放返回与详情布局恢复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: dart
status: completed
dependencies: [TASK-207, TASK-209, TASK-210, TASK-211, TASK-220]
ac-mapping: [AC-074, AC-104]
imp-requirements: [REQ-015, REQ-019]
cross-boundary: false
external-dependency-risk: false
provides: [typed playback return target, source-first movie detail]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-221: Windows 播放返回与详情布局恢复

**功能描述**: 修复退出播放器固定进入缓存页的问题，并把影片详情区块调整为来源、简介、剧照。

**实施边界**: [Windows 播放返回与详情布局恢复](../changes/2026-08-01--windows-playback-return-detail-layout.md)

## 验收条件

- [x] 详情立即 ready 与等待期 ready 播放保留已校验 MovieId，退出回到同一影片详情。
- [x] 缓存页播放退出仍回缓存页；非法或缺失返回 MovieId 安全回退缓存页。
- [x] route 只增加可选 MovieId UUID，不接受自由格式返回路径或敏感播放数据。
- [x] 详情宽窄布局在资料头之后依次显示来源、简介、剧照，既有交互和空状态不回归。

## Definition of Ready

- [x] TASK-207、TASK-209、TASK-210、TASK-211、TASK-220 已完成。
- [x] Windows Release 已复现播放器返回缓存页和详情区块顺序问题。
- [x] Accepted Delta 已冻结返回 query 白名单与详情顺序。

## 实现批次

1. typed player return MovieId 与路由回退测试。
2. 详情来源优先布局与宽窄 Widget 测试。

## Definition of Done

- [x] Focused/Fast、完整差异审计和 Windows Final 全部通过。
- [x] Windows Release 直接启动并可继续实际体验。
- [x] TASK-217 与 TASK-214 保持 pending，交接和追踪矩阵同步。

**依赖**: TASK-207, TASK-209, TASK-210, TASK-211, TASK-220
