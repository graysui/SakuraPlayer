---
id: TASK-322
title: "兼容缺少远程引导器的旧版 Linux Docker 归档"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-321]
ac-mapping: [AC-147, AC-148]
imp-requirements: [REQ-027, REQ-CHG-307]
cross-boundary: false
external-dependency-risk: true
provides: [legacy Linux Docker archive compatibility]
---

# TASK-322: 兼容缺少远程引导器的旧版 Linux Docker 归档

**功能描述**: 让当前远程引导器可以安装已发布但缺少 `install-latest.sh` 的旧版 Linux Docker 归档。

## 验收条件

- [x] `v1.0.1` 这类缺少 `install-latest.sh` 的归档仍能通过布局校验并调用包内 `install.sh`。
- [x] 归档中的 Compose、环境模板、版本文件、安装器、部署说明、许可证和第三方声明仍全部必需。
- [x] 新归档中存在 `install-latest.sh` 时继续复制到持久目录；目标目录中危险的同名符号链接或非普通文件仍拒绝。
- [x] 旧归档兼容逻辑不改变当前目录持久化、host/port 选择、secret 恢复和无 SHA256 用户前置步骤。

## Definition of Ready

- [x] TASK-321 已完成并已推送。
- [x] 用户提供了 `release_archive_invalid` 实际错误。
- [x] 已确认 GitHub `v1.0.1` 归档实际缺少 `install-latest.sh`。

## 实现文件（仅文件名）

**新增**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-04--task-322-legacy-docker-archive-compatibility.md`
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-322.md`

**修改**:

- `backend/install-latest.sh`
- `backend/tests/start/test_linux_installer.py`
- `docs/specs/001-sakuraplayer-v1/contracts/github-release.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`

## Definition of Done

- [x] 旧归档回归测试和完整 TASK-322 定向验证通过。
- [x] 规格、契约、任务索引、追踪矩阵和交接同步。
- [x] 只暂存 TASK-322 文件，并使用中文提交推送。

## 实现证据

- Linux 安装器、发布包、发布 workflow 和部署文档测试 `38 passed`。
- Bash 语法、Ruff format/check、Compose config、`git diff --check` 和 secret 模式审计通过。
