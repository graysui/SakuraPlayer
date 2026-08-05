---
id: TASK-324
title: "MGDB 手动全量同步"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-215, TASK-315]
ac-mapping: [AC-119, AC-150]
imp-requirements: [REQ-022, REQ-CHG-311]
cross-boundary: true
external-dependency-risk: true
provides: [authenticated MGDB full sync request, Windows manual sync control]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-324: MGDB 手动全量同步

**功能描述**: 增加管理员手动创建 MGDB 全量校对请求的后端接口，并在 Windows“设置 - 同步状态”页面提供立即同步按钮和明确反馈。

**实施边界**: [TASK-324 MGDB 手动同步](../changes/2026-08-05--task-324-mgdb-manual-sync.md)

## 外部依赖风险

- **依赖**: 用户配置的 GitHub MGDB 仓库及其 Release 资产。
- **状态**: 未配置、仓库不可达、Release 非法或解密失败都可能导致同步失败。
- **缓解**: API 在来源未配置时拒绝入队；默认测试不联网，worker 继续按既有安全失败和脱敏契约收敛。

## 验收条件

- [x] 受认证管理员可创建固定 `full_reconcile` 请求；未认证拒绝，未配置 MGDB 返回稳定错误且不入队。
- [x] 同模式 `queued/claimed` 活动请求被重复操作复用；只有终态请求时保留审计记录并使用空闲分钟槽新建请求；响应只包含请求 UUID、固定模式和 `created`。
- [x] Windows 同步状态区显示“立即全量同步”按钮；未配置或请求在途时禁用，成功显示已提交并刷新 Settings，失败保留原状态。
- [x] 保存 MGDB 数据源不自动同步；每日增量、每周全量、Release/解密/导入和秘密边界保持不变。
- [x] 功能规格、OpenAPI、错误码、Windows 设置契约、任务索引、追踪矩阵和交接文档同步。

## Definition of Ready

- [x] TASK-215 已交付同步状态和导入总数投影。
- [x] TASK-315 已交付 MGDB 数据源 CAS 和动态 worker source。
- [x] 用户提供保存来源后未同步的实际行为并明确要求手动同步入口。
- [x] TASK-324 Delta 已冻结 full reconcile、鉴权、幂等和客户端反馈边界。

## 实现文件（仅文件名）

**后端**:

- `.dockerignore`
- `backend/docker-compose.yml`
- `backend/docker/api.Dockerfile`
- `backend/tests/run-compose.ps1`
- `backend/tests/docker-compose.test.yml`
- `backend/tests/start/test_docker_entrypoint.py`
- `backend/src/sakuraplayer/api/settings.py`
- `backend/src/sakuraplayer/resources/sync_service.py`
- `backend/tests/integration/api/test_settings_diagnostics.py`

`Dockerfile/.dockerignore` 仅补齐 Final test stage 已有 start 测试所需的发布文件闭包，不改变 runtime 镜像；Final 通过 test-only Compose override 将 bind 数据隔离到临时目录，重启编排排除一次性 `migrate` 服务，并要求 PostgreSQL 最终 TCP 监听建立且目标数据库可查询后才通过健康检查，避免初始化临时服务器误放行迁移，三项均由宿主 Docker 契约测试固定。

**Windows**:

- `windows/lib/features/settings/data/settings_api.dart`
- `windows/lib/features/settings/presentation/settings_controller.dart`
- `windows/lib/features/settings/presentation/settings_page.dart`
- `windows/lib/features/settings/presentation/settings_labels.dart`
- `windows/test/features/settings/qr_settings_test.dart`

**规格**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-05--task-324-mgdb-manual-sync.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
- `docs/specs/001-sakuraplayer-v1/contracts/rest-api.openapi.yaml`
- `docs/specs/001-sakuraplayer-v1/contracts/error-codes.md`
- `docs/specs/001-sakuraplayer-v1/contracts/windows-settings-cache-client.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`

## Definition of Done

- [x] 后端、Windows 实现和相关测试完成。
- [x] Focused、Fast、只读审计和 Final 验证完成，`git diff --check` 通过。
- [x] 任务状态、验收项、证据、交接和追踪矩阵在同一中文提交中更新。

## 验证证据

- 后端 Focused：设置诊断聚焦测试 `1 passed`；Windows Focused：`qr_settings_test.dart` 15 项通过。
- Fast：后端自包含 `914 passed, 11 deselected`；test-image start `143 passed, 9 deselected`；Windows `flutter analyze` 零问题、完整测试 236 项通过。
- Final：Windows Release 构建成功；完整 Compose 通过自包含 `914 passed, 11 deselected` 与 PostgreSQL integration/E2E `129 passed, 16 deselected`，迁移、健康、认证、秘密日志、重启、ready 降级恢复和资源清理均通过。
- Ruff、Dart format、PowerShell 语法、宿主 Docker 契约、完整差异审计、凭据扫描和 `git diff --check` 通过；默认验证未访问真实 MGDB、115、JavDB 写操作或付费 AI。

**依赖**: TASK-215, TASK-315
