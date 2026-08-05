---
id: TASK-323
title: "Linux Docker 数据目录与配置兼容修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-322]
ac-mapping: [AC-148, AC-149]
imp-requirements: [REQ-027, REQ-CHG-308, REQ-CHG-309, REQ-CHG-310]
cross-boundary: false
external-dependency-risk: true
provides: [Linux Docker bind-mounted data directories, persistent network config, legacy database compatibility]
---

# TASK-323: Linux Docker 数据目录与配置兼容修复

**功能描述**: 修复飞牛 NAS 上一键安装后 `.env` 没有保存用户输入、容器数据仍位于 Docker 系统目录，以及旧数据库 PostgreSQL 密码与新 secret 不一致导致迁移失败的问题。

## 验收条件

- [x] 新版 Compose 将 PostgreSQL、永久图片、上游缓存和日志绑定到安装目录下的四个 `data/` 子目录，安装器会创建这些目录。
- [x] 首次一键安装询问的 `SAKURAPLAYER_PUBLISH_HOST` 和 `SAKURAPLAYER_API_PORT` 写入安装目录 `.env` 并供 Compose 使用；已有 `.env` 不再询问或覆盖。
- [x] 旧版 `sakuraplayer_*` named volume 会在首次切换时复制到安装目录对应的 `data/` 子目录，原卷保留；迁移失败会在服务完整启动前停止。
- [x] 使用 `.env` 配置的数据库角色和数据库连接 PostgreSQL，并以当前 `secrets/postgres_password.txt` 同步既有角色密码后再执行迁移；兼容旧数据库和新 secret，不输出 secret 或完整 DSN。
- [x] README、架构、运行配置契约、发布契约、任务索引、追踪矩阵和交接文档与实际部署路径一致。

## Definition of Ready

- [x] TASK-322 已完成并已推送。
- [x] 用户提供了 `.env` 未写回、Docker 路径错误和 `migrate` 密码认证失败的实际现场日志。
- [x] 已确认用户要求不运行测试，由用户自行在 NAS 上验证。

## 实现文件（仅文件名）

**新增**:

- `docs/specs/001-sakuraplayer-v1/changes/2026-08-04--task-323-docker-data-and-config-compatibility.md`
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-323.md`

**修改**:

- `backend/install-latest.sh`
- `backend/install.sh`
- `backend/docker-compose.yml`
- `backend/tests/start/test_docker_entrypoint.py`
- `backend/README.md`
- `backend/README.docker.md`
- `README.md`
- `docs/specs/architecture.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
- `docs/specs/001-sakuraplayer-v1/contracts/runtime-configuration.md`
- `docs/specs/001-sakuraplayer-v1/contracts/github-release.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`

## Definition of Done

- [x] 部署脚本、Compose、旧 named volume 迁移和 PostgreSQL 密码兼容实现完成。
- [x] 正式变更规格、功能规格、契约、任务索引、追踪矩阵、README、架构和交接同步。
- [x] 只暂存 TASK-323 相关文件，并使用中文 Git 提交推送。
- [x] Linux 安装器回归测试 `backend/tests/start/test_linux_installer.py` 通过 `18 passed`；未运行完整 Compose。
- [x] Compose 结构测试已同步为验证四个 `data/` bind mount 和无顶层 named volume。
- [x] PostgreSQL 密码修复命令显式使用配置中的 `POSTGRES_USER` 和 `POSTGRES_DB`，不再依赖可能不存在的默认 `postgres` 数据库角色。

## 实现证据

- 静态差异审计确认：首次 `.env` 才进入交互选择；新 Compose 使用 `./data/...`；旧卷复制使用 root 权限；安装前通过配置角色和数据库同步 PostgreSQL 角色密码；远程引导器的 Docker 调用按需执行。
- 修复后 `backend/tests/start/test_linux_installer.py` 通过 `18 passed`，覆盖 secret、网络配置、归档下载、非法版本、旧归档和运行容器 secret 恢复。`test_docker_entrypoint.py` 已更新，但本机 WSL 未接入 Docker，无法执行其 Compose config；待 CI 和用户飞牛 NAS 验证。
- 飞牛 NAS 后续现场确认旧修复命令错误连接数据库角色 `postgres`；两个安装脚本已显式改用 `.env` 的 `POSTGRES_USER`/`POSTGRES_DB` 并补回归断言。按用户要求，本轮未执行测试，由用户在 NAS 上复验。

**依赖**: TASK-322
