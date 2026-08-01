---
id: TASK-215
title: "首次同步与聚合进度体验修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-213]
ac-mapping: [AC-020, AC-021, AC-119, AC-121, AC-122]
imp-requirements: [REQ-005, REQ-022]
cross-boundary: true
external-dependency-risk: false
provides: [initial AVdb baseline, AVdb imported count, aggregate metadata progress, Chinese Windows statuses]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-215: 首次同步与聚合进度体验修复

**功能描述**: 修复 TASK-213 后真实首次体验发现的同步空窗、AVdb 数量不可见、元数据任务列表过载和英文稳定状态直出问题。

**实施边界**: [TASK-215 首次同步与聚合进度体验](../changes/2026-08-01--task-215-runtime-progress-ux.md)

## 验收条件

- [x] 首次 scheduler 启动幂等排入全量，后续保持每日 30D 与每周全量。
- [x] 设置页的 AVdb 增量/全量状态显示已导入总数。
- [x] 诊断 API 返回守恒的元数据聚合进度和最多 3 个当前番号。
- [x] Windows 元数据区域只显示总体进度与当前番号，不请求/展示逐任务分页。
- [x] Windows 设置和诊断中的 provider、连接、同步与错误提示使用中文映射。

## Definition of Ready

- [x] TASK-213 已完成，真实首次运行问题有运行态证据。
- [x] 用户确认首次全量、AVdb 总数和元数据精简展示语义。
- [x] 变更规格、OpenAPI 和 Windows 客户端契约同步边界已识别。

## 实现批次

1. scheduler 首次全量幂等排队与 settings imported_count。
2. diagnostics metadata_progress 聚合模型。
3. Windows 严格 DTO、单请求 controller、聚合界面与中文映射。
4. Focused、Fast、审计、Final、交接和提交。

## Definition of Done

- [x] 所有验收条件与相关契约测试通过。
- [x] 完整差异审计、`git diff --check` 和分层门禁通过。
- [x] TASK-214 保持 pending，并依赖已完成的 TASK-215。

## 实现证据

- 后端 Focused 11 项、Ruff format/check 和 Fast 788 passed/8 deselected；AVdb 短租约测试改为可控时钟后连续 20 次通过。
- Windows `flutter analyze` 无问题，设置/诊断 Focused 11 项与完整 211 项测试通过，Release 构建成功。
- Compose Final 第三次尝试通过 788 项自包含和 125 项 PostgreSQL integration/E2E；迁移、五服务健康、认证 canary、秘密扫描、重启、ready 降级恢复和隔离资源清理全部完成。
- 性能门禁保持原阈值；隔离宿主负载后 movies/actors/exact/title/alias p95 均通过，四个查询索引断言通过。

**依赖**: TASK-213
