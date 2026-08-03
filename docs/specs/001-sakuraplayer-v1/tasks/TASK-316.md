---
id: TASK-316
title: "GitHub 自动验证与版本发布"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-001, TASK-212, TASK-214, TASK-315]
ac-mapping: [AC-005, AC-008, AC-009, AC-123, AC-128, AC-136, AC-137, AC-138, AC-139, AC-140, AC-141, AC-142]
imp-requirements: [REQ-002, REQ-023, REQ-024, REQ-026]
cross-boundary: false
external-dependency-risk: true
provides: [GitHub verification workflow, Windows GitHub Release, GHCR and Docker Hub backend runtime image, release attestations]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-316: GitHub 自动验证与版本发布

**功能描述**: 建立公开仓库级 GitHub Actions，在 pull request/main 验证源码，在严格版本 tag 上自动发布 Windows 客户端和后端 Docker 镜像。

**实施边界**: [TASK-316 GitHub 自动发布](../changes/2026-08-03--task-316-github-release-automation.md)

**发布契约**: [GitHub 自动发布契约](../contracts/github-release.md)

## 外部依赖风险

- **依赖**: GitHub-hosted Windows/Linux runner、GitHub Actions、GitHub Releases、GHCR 和 Docker Hub。
- **状态**: runner、registry、attestation 或 GitHub API 暂时不可用时发布可能失败。
- **缓解**: tag 发布幂等使用不可变版本，Release 只在全部构建成功后创建；失败后修复源码并使用新版本 tag，不覆盖既有发布事实。

## 验收条件

- [x] pull request/main 执行后端、Docker runtime 和 Windows 离线验证，不读取业务 secret。
- [x] 严格 `vX.Y.Z` tag 与 Flutter 主版本不一致时在发布前失败。
- [x] Windows x64 ZIP、外层 SHA-256 和 artifact attestation 自动生成。
- [x] 单一 Linux amd64 后端 runtime 镜像由同一次构建推送至 GHCR 与 Docker Hub，两处生成相同版本标签、共享 digest 并分别生成 attestation。
- [x] Windows 与 Docker 成功后才创建 GitHub Release 并上传两个 Windows 资产。
- [x] 工作流使用最小权限、完整 Action commit SHA、仓库 token 和专用 Docker Hub Secret，不依赖个人 GitHub PAT 或业务 secret。
- [x] Compose 支持四个后端进程从同一发布镜像运行，源码构建路径保持兼容。
- [x] README 说明 Release 下载、GHCR/Docker Hub 部署、版本策略、校验和未签名边界。

## Definition of Ready

- [x] TASK-001 后端 runtime Docker target 与 Compose 已完成。
- [x] TASK-212 Windows 私有 ZIP、许可证与内容验证脚本已完成。
- [x] TASK-214 Windows 客户端清理已完成。
- [x] TASK-315 公开仓库 README 和 MGDB 用户数据源已完成。
- [x] TASK-316 Delta、发布契约、AC 映射与任务边界已同步。

## 实现文件（仅文件名）

**新增**:

- `.github/workflows/verify.yml`
- `.github/workflows/release.yml`
- `tools/release/validate_version.py`
- `backend/tests/start/test_release_workflows.py`

**修改**:

- `.dockerignore`
- `backend/docker-compose.yml`
- `backend/docker/api.Dockerfile`
- `README.md`
- 功能规格、任务索引、追踪矩阵和会话交接

## 测试说明

- Python 标准库测试验证版本解析、工作流触发、权限、SHA pin、资产名、镜像标签和 Compose 镜像复用。
- 后端 test image 只纳入发布契约所需的 workflow、版本工具、Flutter 版本文件和 Compose，不复制 Windows 业务源码。
- 本地构建 Windows Release ZIP 并复核两个外层资产；本地构建后端 runtime 镜像。
- Fast/Final 保持默认无真实 115、JavDB 写操作和付费 AI。
- 推送后只用 GitHub CLI 检查远程验证与工作流识别；首个正式 tag 不属于自动测试动作。

## Definition of Done

- [x] 实现与静态发布契约测试完成。
- [x] Focused/Fast/Final、本地 Windows/Docker 发布构建和 `git diff --check` 通过。
- [x] GitHub 远程 verify 绿色，release workflow 被 GitHub 正确识别。
- [x] 任务状态、README、交接、契约和追踪矩阵在同一中文提交中更新。

**依赖**: TASK-001, TASK-212, TASK-214, TASK-315
