---
id: TASK-227
title: "影片详情中文简介与重新刮削"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-007, TASK-207, TASK-218, TASK-225]
ac-mapping: [AC-040, AC-041, AC-055, AC-057, AC-074, AC-122]
imp-requirements: [REQ-008, REQ-011, REQ-015, REQ-022]
cross-boundary: true
external-dependency-risk: false
provides: [Chinese-only movie description, movie detail metadata rescrape]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-227: 影片详情中文简介与重新刮削

**功能描述**: 影片详情简介只展示已完成的中文译文，并允许用户从当前番号详情页显式创建或复用最高优先级完整元数据任务。

**实施边界**: [影片详情中文简介与重新刮削](../changes/2026-08-03--movie-detail-chinese-description-rescrape.md)

## 验收条件

- [x] 详情 `description` 只投影 `description_zh`，Windows 不显示 `description_original`；缺失译文显示“暂无中文简介”。
- [x] 认证管理员可按 MovieId 重新刮削，服务端固定使用当前规范化番号、priority 10 和 full retry。
- [x] queued/running full attempt 安全复用，终态创建下一 attempt，活动 enrichment-only 稳定冲突且不产生重复任务。
- [x] Windows 重新刮削按钮在途防重，成功/复用/冲突/失败均显示中文且保留详情状态。
- [x] 历史 attempt、原始简介和既有 translation 付费事实不被修改或自动批量重试。

## Definition of Ready

- [x] 用户已明确要求简介只保留中文译文，并在番号详情页增加最高优先级重新刮削按钮。
- [x] TASK-007/207/218/225 已 completed，元数据队列、详情 DTO、受限详情和翻译 v2 可用。
- [x] 已创建 Accepted Delta，冻结 MovieId 入口、priority 10、活动任务复用和中文-only 投影。
- [x] 后端与 Windows 聚焦测试入口已确认，默认测试无需真实 provider。

## 实施批次

1. 以失败测试冻结中文简介投影和影片级 rescrape 队列事务。
2. 实现后端 queue/service/API、OpenAPI 和错误映射，并运行后端 Focused。
3. 以失败测试实现 Windows gateway/controller/button 和中文状态，并运行 Windows Focused。
4. 运行 Fast、完整差异自审和只读审计，收敛后进入 Final。
5. 运行一次 Final，更新任务、索引、追踪矩阵和交接，并创建独立中文提交。

## 预计实现文件

**修改**:

- `backend/src/sakuraplayer/catalog/query_service.py` - 中文简介投影。
- `backend/src/sakuraplayer/catalog/metadata_queue.py`、`metadata_api.py` - 影片级完整重新刮削事务和 API。
- `backend/tests/unit/catalog/test_catalog_query_service.py`、metadata queue/API tests - 后端回归。
- `windows/lib/features/movies/data/movie_detail_api.dart`、`presentation/movie_detail_controller.dart`、`movie_detail_page.dart` - gateway、状态与按钮。
- `windows/test/features/movies/movie_detail_controller_test.dart`、`movie_detail_page_test.dart` - 客户端回归。
- OpenAPI、目录端口、Windows 详情契约、任务索引、追踪矩阵和 `SESSION-HANDOFF.md` - 契约与生命周期同步。

## Definition of Done

- [x] 所有验收条件、Focused/Fast/Final 和完整差异审计通过。
- [x] OpenAPI、客户端契约、任务状态、索引、追踪矩阵和交接同步。
- [x] 只暂存 TASK-227 相关文件并创建一次中文 Git 提交；TASK-214 保持 pending。

## 完成证据

- Focused：后端中文简介、队列和 API 37 项通过；Windows 影片详情 24 项通过。
- Fast：Ruff format/check、864 项自包含测试、宿主 Docker 配置通过，9 项 infrastructure marker 按既有分层排除；Windows Dart 格式 97 文件无变更、analyze 零问题、233 项 Flutter 测试和 4 项 Fake 用户旅程通过。
- 审计：完整差异、PostgreSQL 行锁与活动唯一约束、OpenAPI/实际路由、客户端迟到响应、窄窗口和中文提示检查收敛；并发收藏状态覆盖问题已修复并回归，`git diff --check` 与秘密扫描通过。
- Final：Windows Release 构建通过；Compose 一次通过 864 项自包含测试、PostgreSQL integration/E2E、迁移、四服务健康、认证 canary、持久日志秘密扫描、重启、ready 降级恢复和隔离资源清理。默认测试未访问真实 provider、115 或付费 AI。

**依赖**: TASK-007, TASK-207, TASK-218, TASK-225
