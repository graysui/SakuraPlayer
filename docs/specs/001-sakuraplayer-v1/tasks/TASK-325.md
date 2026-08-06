---
id: TASK-325
title: "AI 配置恢复、翻译瘦身与 Docker 原地升级"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-208, TASK-225, TASK-323]
ac-mapping: [AC-054, AC-055, AC-056, AC-057, AC-119, AC-148, AC-149, AC-151]
imp-requirements: [REQ-011, REQ-022, REQ-027, REQ-CHG-312, REQ-CHG-313, REQ-CHG-314, REQ-CHG-315, REQ-CHG-316, REQ-CHG-317]
cross-boundary: true
external-dependency-risk: false
provides: [authoritative AI settings restore, title and description only translation v3, in-place Docker release upgrade]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-325: AI 配置恢复、翻译瘦身与 Docker 原地升级

**功能描述**: 修复 Windows AI 配置重启回显，移除付费翻译中的无关元数据和演员简介请求，并让现有 Linux/NAS Docker 部署可保留全部数据原地升级到当前 Release。

**实施边界**: [TASK-325 AI 配置恢复、翻译瘦身与 Docker 原地升级](../changes/2026-08-06--task-325-ai-settings-translation-docker-upgrade.md)

## 验收条件

- [x] AI replace 后以权威 GET 更新 Windows 状态；页面重建或客户端重启后显示持久化的 base URL、model、timeout 和 configured，不回显 API key。
- [x] 新 AI 调用只包含当前影片标题或影片简介；请求不含番号、演员、厂商、系列、标签原值，演员简介不再创建 AI 调用或新记录。
- [x] `sakuraplayer-zh-v3` 在本地占位和恢复 protected 片段，严格拒绝缺失、重复、变形或伪造占位符，并显著收紧短标题和短简介的 `max_tokens`。
- [x] v1/v2 付费派发与历史演员译文事实保持不变；v3 使用新业务键，不自动批量重派历史状态。
- [x] 现有官方 SemVer Docker 部署可原地升级且相同版本幂等；降级、自定义、digest、latest 或非法镜像配置在发布文件覆盖前拒绝。
- [x] Docker 升级前后的 `.env` 非镜像配置、`secrets/`、`data/`、PostgreSQL 设置与已刮削数据保持不变，不删除旧 named volume 或执行 `down -v`。
- [x] 功能规格、元数据/Windows/运行配置/GitHub 发布契约、README、任务索引、追踪矩阵和交接文档同步。

## Definition of Ready

- [x] TASK-208 已交付 Windows 设置页与对象级 CAS。
- [x] TASK-225 已交付 v2 翻译协议、付费幂等和硅基流动 profile。
- [x] TASK-323 已交付持久安装目录 bind mount 与旧数据迁移。
- [x] 用户明确 AI 只翻译标题和影片简介，并要求现有 Docker 保留数据原地升级。
- [x] TASK-325 Delta 已冻结配置恢复、v3 请求、历史事实和升级拒绝边界。

## 实现文件（仅文件名）

**后端与部署**:

- `backend/src/sakuraplayer/catalog/translation/adapter.py`
- `backend/src/sakuraplayer/catalog/translation/service.py`
- `backend/tests/unit/catalog/translation/test_adapter.py`
- `backend/tests/unit/catalog/translation/test_service.py`
- `backend/tests/integration/catalog/test_translation_service.py`
- `backend/tests/integration/api/test_settings_diagnostics.py`
- `backend/install-latest.sh`
- `backend/tests/start/test_linux_installer.py`
- `backend/tests/unit/catalog/providers/test_runtime.py`

**Windows**:

- `windows/lib/features/settings/presentation/settings_controller.dart`
- `windows/lib/features/settings/presentation/settings_page.dart`
- `windows/test/features/settings/qr_settings_test.dart`

**规格与发布**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-06--task-325-ai-settings-translation-docker-upgrade.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
- `docs/specs/001-sakuraplayer-v1/contracts/metadata-providers.md`
- `docs/specs/001-sakuraplayer-v1/contracts/windows-settings-cache-client.md`
- `docs/specs/001-sakuraplayer-v1/contracts/runtime-configuration.md`
- `docs/specs/001-sakuraplayer-v1/contracts/github-release.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`
- `README.md`
- `backend/README.md`

## Definition of Done

- [x] 后端、Windows、安装器实现和相关测试完成。
- [x] Focused、Fast、只读审计和 `git diff --check` 完成；Final 唯一失败为既有 TASK-011 影片列表 p95 在主机高负载下达到 613.8ms，用户明确接受该性能例外并要求不重跑门禁。
- [x] 任务状态、验收项、证据、交接和追踪矩阵在同一中文提交中更新。

## 验证证据

- Focused：翻译与配置 48 项、Linux 安装器 32 项、Windows settings 16 项通过；锁定 Ruff、Bash 语法与 Docker 配置断言通过。
- Fast：后端自包含 `927 passed, 11 deselected`；Windows `flutter analyze` 零问题、完整测试 237 项通过。
- Final 尝试 1：自包含 `931 passed, 11 deselected`；PostgreSQL integration/E2E 中 128 项通过，唯一失败是未被本任务修改的 TASK-011 影片列表 p95 `613.8ms` 未满足 `<500ms` 断言。临时 Compose 容器、网络和镜像已清理；用户于 2026-08-06 明确接受该性能门禁例外并要求直接提交。
- 默认验证未访问真实付费 AI、115、JavDB 写操作或 MGDB 网络；完整差异审计未发现剩余任务内 P0/P1/P2。

**依赖**: TASK-208, TASK-225, TASK-323
