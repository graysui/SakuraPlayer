---
id: TASK-315
title: "MGDB 用户数据源与 Windows 命名"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-208, TASK-214]
ac-mapping: [AC-018, AC-019, AC-031, AC-083, AC-119]
imp-requirements: [REQ-005, REQ-007, REQ-004]
cross-boundary: true
external-dependency-risk: true
provides: [MGDB source CAS settings, user-selected Release source, Windows MGDB naming]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-315: MGDB 用户数据源与 Windows 命名

**功能描述**: 移除后端内置 AVdb GitHub 仓库，增加管理员输入的 MGDB 数据源配置，并将 Windows 可见 AVdb 名称改为 MGDB。

**实施边界**: [TASK-315 MGDB 用户数据源](../changes/2026-08-03--task-315-mgdb-user-source.md)

**规格映射**: AC-018、AC-019、AC-031、AC-083、AC-119

## 外部依赖风险

- **依赖**: 用户提供的 GitHub 仓库及其 Release 资产。
- **状态**: 未配置、仓库不存在、Release 结构错误和下载失败都可能发生。
- **缓解**: 只允许 GitHub HTTPS 仓库地址；默认测试使用 MockTransport，不访问真实仓库；未配置时不联网。

## 验收条件

- [x] 设置 API 使用 `mgdb.source` 加密 envelope 和对象级 CAS，GET/PATCH 不返回磁力或其他秘密。
- [x] 数据源只接受规范化 GitHub HTTPS 仓库 URL；后端不再写死主/备用第三方仓库。
- [x] worker 每次同步任务读取最新用户来源；未配置时返回稳定 `mgdb_source_not_configured`，不发起 HTTP 请求。
- [x] Windows 设置页可保存、清除 MGDB 数据源，且 CAS 冲突可刷新；可见的 AVDB 文案改为 MGDB。
- [x] 既有 AVDB Release 资产、解密、磁力加密存储和内部兼容字段保持不变。

## Definition of Ready

- [x] TASK-208 设置 API、Windows settings gateway/controller 和现有加密设置仓储已完成。
- [x] TASK-214 Windows 清理已完成，现有前端命名和设置测试可作为回归基线。
- [x] TASK-315 Delta 已同步功能规格、契约、OpenAPI、任务索引和追踪矩阵。

## 实现文件（仅文件名）

**修改**:

- `backend/src/sakuraplayer/resources/avdb_release.py`
- `backend/src/sakuraplayer/resources/avdb_worker.py`
- `backend/src/sakuraplayer/api/settings.py`
- `backend/src/sakuraplayer/api/__main__.py`
- `backend/src/sakuraplayer/worker/__main__.py`
- `windows/lib/features/settings/data/settings_api.dart`
- `windows/lib/features/settings/presentation/settings_controller.dart`
- `windows/lib/features/settings/presentation/settings_page.dart`
- `windows/lib/features/settings/presentation/settings_labels.dart`
- `windows/lib/features/library/data/movies_api.dart`
- `windows/lib/features/movies/data/movie_detail_api.dart`

**测试**:

- `backend/tests/unit/resources/test_avdb_release.py`
- `backend/tests/unit/resources/test_avdb_worker.py`
- `backend/tests/integration/api/test_settings_diagnostics.py`
- `windows/test/features/settings/qr_settings_test.dart`
- `windows/test/features/library/library_controller_test.dart`

## 测试说明

- URL/仓库规范化、未知主机、userinfo/query/fragment、空配置和 CAS 冲突。
- Release client 只请求配置仓库，动态 worker source 不重启生效；磁力和秘密扫描保持通过。
- Flutter 严格 DTO、gateway payload、设置页面输入/清除、MGDB 文案和既有筛选/详情解析回归。

## Definition of Done

- [x] 后端、Windows 实现和相关测试完成。
- [x] Focused/Fast/Final 验证完成，`git diff --check` 通过。
- [x] 任务状态、交接、契约和追踪矩阵在同一中文提交中更新。

**依赖**: TASK-208, TASK-214
