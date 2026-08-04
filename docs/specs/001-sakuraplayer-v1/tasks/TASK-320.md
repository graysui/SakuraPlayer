---
id: TASK-320
title: "Linux 单命令 Docker 发布引导"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-318, TASK-319]
ac-mapping: [AC-140, AC-142, AC-143, AC-144, AC-147]
imp-requirements: [REQ-025, REQ-026, REQ-027]
cross-boundary: false
external-dependency-risk: true
provides: [single-command Linux Docker bootstrap, automatic latest release download]
---

# TASK-320: Linux 单命令 Docker 发布引导

**功能描述**: 为 Linux/NAS 新用户提供无需手动下载 Release、解压和 SHA256 校验的单命令 Docker 部署入口，同时保留原有本地发布包安装器、发布校验文件和高级手动 Compose 路径。

## 验收条件

- [x] `curl -fsSL https://raw.githubusercontent.com/graysui/SakuraPlayer/main/backend/install-latest.sh | bash` 可解析最新正式 `vX.Y.Z`，下载同版本 `SakuraPlayer-Docker-X.Y.Z.tar.gz`，解压并调用包内 `install.sh`。
- [x] 推荐命令不要求用户手动下载 Release、手动解压或执行 SHA256；发布流程仍生成 `.sha256` 和 artifact attestation，高级路径继续可选使用。
- [x] 最新版本 URL 非规范、下载失败、归档损坏或归档布局异常时，在 Compose 启动前明确失败，不泄漏敏感文本，并清理临时目录。
- [x] 发布归档携带远程引导器和本地安装器，归档白名单、可重复性、权限、无 secret/业务数据约束继续通过。
- [x] README、后端部署说明、发布契约、功能规格、任务索引、追踪矩阵和会话交接均反映新手单命令路径及保留的高级路径。

## Definition of Ready

- [x] TASK-318、TASK-319 completed，现有 Linux 发布归档和本地安装器可复用。
- [x] 用户已明确要求一段命令自动完成部署，并取消用户端 SHA256 前置步骤。
- [x] 远程引导与本地安装职责分离，未改变 secret、loopback、Compose 健康等待或发布资产生成安全语义。

## 实现文件（仅文件名）

**新增**:

- `backend/install-latest.sh`
- `docs/specs/001-sakuraplayer-v1/changes/2026-08-04--task-320-one-command-docker-bootstrap.md`
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-320.md`

**修改**:

- `backend/README.docker.md`
- `backend/README.md`
- `backend/tests/start/test_docker_release_bundle.py`
- `backend/tests/start/test_linux_installer.py`
- `backend/tests/start/test_release_workflows.py`
- `.github/workflows/release.yml`
- `tools/release/build_docker_bundle.py`
- `README.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
- `docs/specs/001-sakuraplayer-v1/contracts/github-release.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`

## Definition of Done

- [x] 引导脚本、归档、文档和正式规格实现一致。
- [x] 远程引导器定向测试、归档测试、workflow 契约、Shell 语法和必要 Compose config 通过。
- [x] 完整差异审计、`git diff --check`、secret 扫描通过，未暂存用户未跟踪资料。
- [x] 任务状态与交接在同一中文 Git 提交中更新。

## 实现证据

- Linux 容器定向部署测试：`33 passed`。
- Ruff format/check、`bash -n backend/install.sh backend/install-latest.sh`、`docker compose ... config --quiet`、`git diff --check` 和 secret 模式扫描通过。
- 全部 `tests/start` 额外运行时的 5 个失败属于容器缺少 Docker CLI/PowerShell及既有 worker 超时，未纳入本任务相关测试证据。
