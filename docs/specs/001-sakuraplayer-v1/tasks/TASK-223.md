---
id: TASK-223
title: "真实目录响应兼容修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-206, TASK-207, TASK-216, TASK-222]
ac-mapping: [AC-042, AC-047, AC-048, AC-051, AC-052, AC-063, AC-069, AC-074, AC-075]
imp-requirements: [REQ-008, REQ-009, REQ-010, REQ-013, REQ-014, REQ-015]
cross-boundary: true
external-dependency-risk: true
provides: [client-safe gfriends projection, verified catalog cover projection, production translation evidence]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-223: 真实目录响应兼容修复

**功能描述**: 修复正式女优和影片详情响应被 Windows 严格 DTO 拒绝的问题，明确永久封面恢复状态与客户端占位边界，并核对简介中文翻译的真实失败事实。

**实施边界**: [真实目录响应兼容与可选元数据状态](../changes/2026-08-02--catalog-response-compatibility.md)

## 验收条件

- [x] GFriends 合法数字 `t` query 只在后端客户端投影时移除，Windows URL 白名单不放宽。
- [x] 非法可选头像/写真按单图缺失隔离，女优列表和影片详情保持可消费。
- [x] 只有已有校验摘要的 cover 投影 `cover_url`；无摘要 retry_pending 安全占位返回 null，最近成功封面保留且详情可打开。
- [x] 正式排行榜、媒体库和搜索命中影片均可进入同一详情 DTO。
- [x] 正式 AI 翻译只读核验给出成功数量和稳定失败码，不访问付费翻译。

## Definition of Ready

- [x] TASK-206、TASK-207、TASK-216、TASK-222 已完成，TASK-214 保持 pending。
- [x] 正式 API、数据库、图片卷和 Windows DTO 已复现并定位共同失败字段。
- [x] Accepted Delta 已冻结 GFriends 规范化、图片状态投影和翻译只读边界。

## 实现批次

1. 以失败测试冻结 GFriends 客户端安全投影和可选资产失败隔离。
2. 以失败测试冻结 ready-only cover 投影和 retry_pending 客户端占位。
3. Focused/Fast、完整差异审计和 Final。
4. 部署普通 Compose/Windows Release，验证正式页面、图片状态和翻译聚合；不替用户批量重试刮削或富化任务。

## Definition of Done

- [x] 后端/Windows Focused、Fast、静态检查、只读审计、Compose Final 和 Windows Final 全部通过。
- [x] 正式女优、详情、榜单/搜索导航、ready/failed cover 与翻译聚合证据通过。
- [x] TASK-214 保持 pending，任务索引、契约、追踪矩阵和交接同步。

## 完成证据

- Fast：后端 `842 passed, 9 deselected`，Windows `228 passed`，Ruff format/check 与 `flutter analyze` 通过。
- Final：Compose 自包含 `842 passed, 9 deselected`、PostgreSQL integration/E2E `127 passed, 16 deselected`；Windows Fake 集成 1 项、用户旅程 4 项、Release 和 34 文件包扫描通过。
- 正式只读核验：女优/写真/影片详情投影无 query，Windows 严格 DTO 通过；1958 张已验证封面正常投影，2115 条无摘要封面返回 null，永久图片缺失 0。
- 翻译只读核验：140952 部影片中 `title_zh=0`、`description_zh=0`；稳定失败为 `translation_guardrail_failed` 与 `translation_upstream_error`，未调用付费 AI。
- 按用户要求不逐部重试；遗留的 1018 个未执行 images-only 队列任务已精确移除，活动 images-only 任务为 0，刮削由用户手动发起。

**依赖**: TASK-206, TASK-207, TASK-216, TASK-222
