---
id: TASK-001
title: "后端工程、Compose 与 Schema 门禁"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: []
ac-mapping: [AC-005, AC-008, AC-009, AC-123, AC-124, AC-125, AC-126, AC-127, AC-133, AC-134]
imp-requirements: [REQ-002, REQ-023, REQ-024, REQ-025]
cross-boundary: false
external-dependency-risk: false
provides: [backend scaffold, docker compose, alembic head, health endpoints]
---

# TASK-001: 后端工程、Compose 与 Schema 门禁

**功能描述**: 建立 Python/FastAPI/PostgreSQL 后端骨架、Docker Compose 私有部署、健康检查和启动 Schema 门禁。

**规格映射**: AC-005、AC-008、AC-009、AC-123 至 AC-127、AC-133、AC-134

## 验收条件

- [ ] Docker Compose 至少启动 API、scheduler/worker 和 PostgreSQL，PostgreSQL 不映射宿主公网；对应 AC-123。
- [ ] PostgreSQL、永久图片、清单缓存和必要日志使用独立持久卷；后端提供健康检查，重启可进入恢复流程；对应 AC-124、AC-127。
- [ ] 部署文档明确仅面向家庭网络/VPN、无公网向导、无自动数据库或图片备份；对应 AC-125、AC-126。
- [ ] Windows 第一阶段所需后端契约、Windows 私有安装约束和 GPLv3/第三方声明骨架存在；对应 AC-005、AC-008、AC-009。
- [ ] Compose 默认只发布 loopback，远程地址必须显式配置，部署文档要求 HTTPS 或可信 VPN；对应 AC-134。
- [ ] 设置、JWT、播放和 bootstrap 四类 secret 名称/格式固定且不复用，bootstrap secret 可供 TASK-002 使用；对应 AC-133。

## Definition of Ready

- [ ] 已读取项目架构、技术计划、数据模型和 REST 契约。
- [ ] Docker、PostgreSQL 17.5 和 Python 3.10.16 可用。
- [ ] 已读取 `contracts/runtime-configuration.md`，不得另起环境变量名称或密钥用途。
- [ ] 旧 SakuraMedia Schema 不作为迁移输入。

## 技术上下文

- **模式**: 模块化单体；API、scheduler、worker 共享领域包但独立入口。
- **数据库**: SQLAlchemy 2.0.41 + Alembic 1.16.2，未知 Schema 明确拒绝启动。
- **契约**: OpenAPI 3.1 `rest-api.openapi.yaml`，错误结构使用 `code/message/details/request_id`。
- **目录**: `backend/src/sakuraplayer/{identity,resources,catalog,discovery,cloud_cache,playback,events,shared,api,worker,scheduler}`。
- **参考**: 只移植 `avmedia` 的可验证基础设施，不引入 qBittorrent、Qdrant、永久媒体库或下载器。

## 实现文件（仅文件名）

**创建**:

- `backend/pyproject.toml` - 固定 Python 依赖和 pytest 配置。
- `backend/docker-compose.yml` - api、scheduler、worker、postgres 与独立卷。
- `backend/.env.example` - 不含秘密的普通配置与 Secret 文件名示例。
- `backend/docker/api.Dockerfile` - API 镜像。
- `backend/src/sakuraplayer/api/app.py` - FastAPI 组合根和健康路由。
- `backend/src/sakuraplayer/shared/schema_guard.py` - 启动 Schema 版本检查。
- `backend/alembic/versions/0001_initial_skeleton.py` - 初始迁移骨架。
- `backend/tests/start/test_docker_entrypoint.py` - Compose 配置和入口检查。
- `backend/tests/start/test_schema_guard.py` - 兼容/未知 Schema 拒绝测试。

## 测试说明

**单元测试**:

- `schema_guard`: 验证 head Schema 允许启动、旧/未知版本明确拒绝。
- 配置加载: 验证生产模式缺少数据库或主密钥入口时失败，且不打印秘密。
- 配置加载还要拒绝密钥格式错误、四用途复用和同时设置 `_FILE`/明文变量。

**集成测试**:

- 启动 Compose 后检查 API、worker、scheduler、PostgreSQL 健康状态和独立卷挂载。
- 验证 PostgreSQL 端口没有公开映射，进程重启后健康检查恢复。

**边界条件**:

- 缺失环境变量、数据库未就绪、迁移未完成、重复执行迁移、远程明文发布未显式确认。

## Definition of Done

- [ ] 骨架、迁移、Compose、健康检查和许可证声明完成。
- [ ] 规格映射的测试全部通过。
- [ ] 未引入未批准技术或公网部署入口。

**依赖**: None

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-001.md"`
