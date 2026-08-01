---
id: TASK-222
title: "实际体验内容恢复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-216, TASK-217, TASK-218, TASK-221]
ac-mapping: [AC-040, AC-043, AC-045, AC-051, AC-052, AC-069, AC-071, AC-072, AC-104, AC-121, AC-122]
imp-requirements: [REQ-008, REQ-009, REQ-010, REQ-014, REQ-019, REQ-022]
cross-boundary: true
external-dependency-risk: true
provides: [navigation-stack playback return, DMM detail parsing, explicit ranking recovery, visible metadata failure count]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-222: 实际体验内容恢复

**功能描述**: 修复 Release 实测的播放器返回、DMM 简介、空排行榜和刮削失败计数问题，并验证 GFriends 头像刷新。

**实施边界**: [实际体验内容恢复](../changes/2026-08-01--runtime-content-recovery.md)

## 验收条件

- [x] 应用内三类播放入口返回进入播放器前页面，直接深链仍回缓存页。
- [x] DMM 两阶段精确解析通过 fixture，真实只读连接测试可用。
- [x] 正式当前榜单 transient failed 使用既有手动重试语义显式恢复，日/周/月产生可见内容。
- [x] 既有 DMM warning 只显式重试 DMM 富化，新任务可持久化简介。
- [x] 诊断进度显示失败数量与当前番号，不展示逐任务列表。
- [x] 女优页刷新后显示正式首屏已有映射的头像，未匹配条目保持占位。

## Definition of Ready

- [x] TASK-216/217/218/221 已完成，TASK-214 保持 pending。
- [x] 当前 Release 与普通 Compose 已复现问题，并核对真实数据库和连接测试。
- [x] DMM 根因为搜索页未进入详情页；参考实现和严格安全边界已确认。
- [x] 当前榜单 402 个唯一番号中 230 个为 transient failed、10 个为明确未找到、49 个仍 queued、109 个 core ready。
- [x] GFriends current、首屏 API 映射和 Windows 主机图片读取证据已确认。

## 实施批次

1. 以失败测试冻结导航栈返回和诊断失败计数。
2. 以失败 fixture 冻结 DMM 搜索、精确详情匹配和详情简介解析。
3. Focused/Fast、完整差异审计和 Final。
4. 正式环境显式恢复榜单/DMM、验证 DMM/GFriends/排行榜并启动 Windows Release。
5. 更新任务、交接并创建独立中文 Git 提交。

## Definition of Done

- [x] Focused/Fast/审计/Compose Final/Windows Final 全部通过。
- [x] 正式 DMM、排行榜、女优头像和进度显示证据通过。
- [x] TASK-214 保持 pending，交接和追踪矩阵同步。

**依赖**: TASK-216, TASK-217, TASK-218, TASK-221
