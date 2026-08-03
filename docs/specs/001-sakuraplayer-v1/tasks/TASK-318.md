---
id: TASK-318
title: "Linux 一键安全部署与 Docker 发布包"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-316, TASK-317]
ac-mapping: [AC-120, AC-123, AC-127, AC-133, AC-134, AC-140, AC-142, AC-143, AC-144]
imp-requirements: [REQ-022, REQ-023, REQ-025, REQ-026, REQ-027]
cross-boundary: false
external-dependency-risk: false
provides: [idempotent Linux installer, automatic host secrets, versioned Docker deployment asset]
---

# TASK-318: Linux 一键安全部署与 Docker 发布包

**功能描述**: 为 Linux/NAS 新用户提供免 Git 的官方 Docker 部署包和单命令安装入口，自动生成并持久化五个启动 secret、创建发布配置、拉取并健康启动完整 Compose，同时保持现有安全与恢复语义。

## 验收条件

- [x] 安装脚本可从任意工作目录运行，首次执行自动生成发布版 `.env` 和五个独立 secret，并使用完整 SemVer Docker Hub 镜像启动 Compose。
- [x] 有效 `.env` 和 secret 在重复执行、服务重启或前一次启动失败后均保持原值；脚本只收紧目录/文件权限，不静默覆盖。
- [x] 符号链接、非普通文件、非法格式、用途复用和并发安装被明确拒绝，且失败信息不包含任何 secret 值。
- [x] 默认 API 仍只绑定 `127.0.0.1`；脚本 stdout/stderr 只显示阶段、访问地址和 bootstrap 文件路径，不直接显示初始化口令。
- [x] 未来正式 Release 生成 `SakuraPlayer-Docker-X.Y.Z.tar.gz`、同名 `.sha256` 和 artifact attestation，包内不含 secret、`.env` 或业务数据。
- [x] README 与后端部署说明以下载部署包并运行 `./install.sh` 为新手主路径，手动 Compose 保留为高级路径。

## Definition of Ready

- [x] TASK-316、TASK-317 completed，Release workflow 与双 registry 已实际发布。
- [x] 五个 secret 的格式、用途隔离、bootstrap 生命周期和默认 loopback 契约已冻结。
- [x] 用户确认采用官方一键安装脚本方案。
- [x] 用户明确批准本任务不执行三层验证和完整 Compose。

## 实现文件（仅文件名）

**新增**:

- `backend/install.sh`
- `backend/README.docker.md`
- `backend/tests/start/test_linux_installer.py`
- `docs/specs/001-sakuraplayer-v1/changes/2026-08-03--task-318-one-command-docker-install.md`
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-318.md`

**修改**:

- `.gitattributes`
- `.github/workflows/release.yml`
- `tools/release/validate_version.py`
- `backend/tests/start/test_release_workflows.py`
- `README.md`
- `backend/README.md`
- 运行配置/发布契约、功能规格、任务索引、追踪矩阵和会话交接

## 验证例外

用户明确批准本任务不执行 Focused/Fast/Final 三层验证，也不运行完整 Compose。任务仍必须通过定向安装脚本测试、发布契约测试、Shell 语法、真实 Compose config、发布包 dry-run、差异审计、`git diff --check` 与 secret 扫描；不得降低安全断言或扩大跳过范围。

## Definition of Done

- [x] 变更规格、功能规格、契约、任务索引和追踪映射一致。
- [x] 安装脚本安全、幂等、失败可重试且不泄漏 secret。
- [x] 发布包内容、版本、SHA-256、Release 依赖与 attestation 契约有自动测试。
- [x] README 新手路径与实际脚本一致，手动路径和网络/备份警告仍可见。
- [x] 用户批准的定向验证、完整差异审计和 `git diff --check` 通过。
- [x] 任务状态与交接在同一中文提交中更新。

## 实现证据

- 定向 Ruff、`bash -n` 与 30 项安装器、发布包、工作流和部署文档测试通过。
- 实际生成 `SakuraPlayer-Docker-1.0.0.tar.gz`，7 文件白名单、SHA-256、可重复归档与 `install.sh` 0755 权限通过。
- 在隔离临时目录生成 `.env` 和测试 secret 后，真实 `docker compose config --quiet` 通过；临时目录已清理。
- `git diff --check` 与定向 secret 扫描通过。按用户批准，本任务未执行 Focused/Fast/Final 三层验证，也未运行完整 Compose。

**依赖**: TASK-316, TASK-317
