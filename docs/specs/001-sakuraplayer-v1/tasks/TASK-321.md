---
id: TASK-321
title: "Linux Docker 持久化安装与网络配置选择"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-320]
ac-mapping: [AC-134, AC-143, AC-144, AC-147, AC-148]
imp-requirements: [REQ-025, REQ-027, REQ-CHG-307]
cross-boundary: false
external-dependency-risk: true
provides: [persistent Linux Docker deployment, interactive private-network configuration]
---

# TASK-321: Linux Docker 持久化安装与网络配置选择

**功能描述**: 修复 Linux 一键 Docker 引导器把运行配置留在临时目录的问题，并让首次安装者选择服务器私网 IPv4 地址与 API 端口。

## 验收条件

- [x] 在 `/vol1/1000/docker/Sakuraplayer` 等当前目录执行一键命令时，发布文件、`.env`、`secrets/` 和 bootstrap token 持久保存在该目录；下载/解压临时目录在退出时清理。
- [x] 首次交互安装从 `/dev/tty` 询问 `SAKURAPLAYER_PUBLISH_HOST` 与 `SAKURAPLAYER_API_PORT`，例如 `192.168.1.50` 和 `8000`；直接回车或无 TTY 使用 `127.0.0.1:8000`。
- [x] host 只接受合法 IPv4 且拒绝 `0.0.0.0`，端口只接受 `1..65535`；校验失败发生在 Compose 启动前。
- [x] 已有 `.env` 保留原值；已有有效 secret 不覆盖。上一版脚本已启动的同项目容器仍运行时，缺失的宿主 secret 可从 `/run/secrets/` 恢复，无法完整恢复时拒绝继续。
- [x] 成功输出显示实际访问地址和持久 bootstrap token 文件路径，任何 secret 值都不进入输出或配置参数。

## Definition of Ready

- [x] TASK-320 已完成并提供远程 Release 引导器。
- [x] 运行配置契约已冻结默认 loopback、端口范围和 secret 文件边界。
- [x] 用户已明确要求一键脚本中选择服务器实际私网地址与 API 端口。

## 实现文件（仅文件名）

**新增**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-04--task-321-persistent-docker-install.md`
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-321.md`

**修改**:

- `backend/install-latest.sh`
- `backend/install.sh`
- `backend/tests/start/test_linux_installer.py`
- `backend/README.md`
- `backend/README.docker.md`
- `README.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
- `docs/specs/001-sakuraplayer-v1/contracts/runtime-configuration.md`
- `docs/specs/001-sakuraplayer-v1/contracts/github-release.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`

## Definition of Done

- [x] 持久目录、网络选择、恢复逻辑和安全校验实现完成。
- [x] 定向安装器测试、发布包/文档契约测试、Bash 语法、Compose config、差异和 secret 审计通过。
- [x] 正式变更规格、功能规格、契约、任务索引、追踪矩阵、README 和交接一致。
- [x] 只暂存 TASK-321 相关文件，并在同一中文提交中更新任务状态与交接。

## 实现证据

- Linux 定向安装器、发布包白名单/可重复性、发布 workflow 和部署文档测试 `37 passed`，覆盖默认配置、指定 `192.168.1.50:8000`、非法网络值、持久化目标目录、临时目录清理和运行容器 secret 恢复。
- Bash 语法、Python 编译、Ruff format/check、Compose config、`git diff --check` 和 secret 模式审计通过。

**依赖**: TASK-320
