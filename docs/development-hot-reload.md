# SakuraPlayer 开发期热更新指南

## 1. 目的与状态

本文说明如何为 SakuraPlayer 建立接近 `npm run dev` 的本地开发体验，减少修改代码后的重复完整构建。

本文当前是一份开发流程提案。Windows Flutter 热重载已经可用；后端 Compose Watch 需要先新增本文所示的开发覆盖文件。开发期热更新只用于快速反馈，不能替代任务要求的 Focused、Fast、Final 验证、完整 Compose 构建或发布构建。

## 2. 当前为什么需要重新构建

当前后端镜像在构建时通过 [api.Dockerfile](../backend/docker/api.Dockerfile) 将 `backend/src` 复制进镜像，[docker-compose.yml](../backend/docker-compose.yml) 没有挂载本地源码，也没有配置 Compose Watch。因此宿主机上的 Python 修改不会自动进入已经运行的容器。

后端不只有 API：`api`、`worker` 和 `scheduler` 都是常驻进程。API 入口当前也没有启用 Uvicorn reload。只给 API 增加 `--reload` 会导致 worker 和 scheduler 继续运行旧代码，不适合作为本项目的完整开发方案。

推荐的开发模式如下：

| 修改类型 | 开发期行为 | 是否完整重建 |
|---|---|---|
| Flutter Dart/UI | Hot Reload | 否 |
| Flutter 启动初始化 | Hot Restart | 通常否 |
| Python `backend/src` | 同步源码并重启三个后端进程 | 否 |
| Python 依赖、Dockerfile、entrypoint | Compose Watch rebuild | 是 |
| Alembic 迁移 | 显式构建、迁移并重启 | 是 |
| Windows 插件、CMake、C++ runner | 停止后重新 `flutter run` | 是 |
| Release/Final 验证 | 使用正式流程完整构建 | 是 |

## 3. Windows Flutter 热重载

### 3.1 启动

首次启动仍需构建一次 Windows debug 程序：

```powershell
cd windows
flutter pub get
flutter run -d windows
```

应用启动后，在登录前设置页把后端地址配置为：

```text
http://127.0.0.1:8000
```

当前代码尚未实际读取 `SAKURAPLAYER_DEFAULT_API_BASE_URL` 的 Dart define，因此不要把 `--dart-define=SAKURAPLAYER_DEFAULT_API_BASE_URL=...` 当作现有可用能力。契约与实现的差异应通过独立任务修复，不在开发文档中静默假定已经实现。

### 3.2 修改后的操作

在运行 `flutter run` 的终端中：

| 按键 | 作用 | 适用情况 |
|---|---|---|
| `r` | Hot Reload | 普通 Dart 逻辑、布局、颜色和组件修改 |
| `R` | Hot Restart | 初始化逻辑、全局状态或热重载没有生效 |
| `q` | 停止应用 | 需要修改原生工程或重新完整启动 |

VS Code 或 Android Studio 可以配置保存文件时自动 Hot Reload。Hot Reload 会尽量保留当前页面和内存状态；如果需要重新执行 `main()` 和初始化流程，应使用 Hot Restart。

以下修改通常需要停止应用后重新运行 `flutter run -d windows`：

- `pubspec.yaml` 中的依赖或资源声明；
- Flutter 原生插件；
- `windows/` 下的 CMake、C++ runner 或打包配置；
- 无法通过 Hot Restart 重新初始化的原生状态；
- Release 构建。

## 4. 后端 Compose Watch 方案

### 4.1 前提

执行以下命令确认 Compose 支持 Watch：

```powershell
docker compose version
docker compose watch --help
```

当前开发机的 Docker Compose v5.1.4 支持该功能。

### 4.2 建议的开发覆盖文件

新增 `backend/docker-compose.dev.yml`，不要把开发期源码同步配置写入正式 Compose：

```yaml
x-app-develop: &app-develop
  watch:
    - action: sync+restart
      path: ./src
      target: /workspace/backend/src
      ignore:
        - "**/__pycache__/**"
        - "**/*.pyc"
    - action: rebuild
      path: ./pyproject.toml
    - action: rebuild
      path: ./docker/api.Dockerfile
    - action: rebuild
      path: ./docker/entrypoint.sh

services:
  api:
    develop: *app-develop
  worker:
    develop: *app-develop
  scheduler:
    develop: *app-develop
```

这里必须同时监视 `api`、`worker` 和 `scheduler`。Python 源码变化使用 `sync+restart`：Compose 把变化同步到容器，然后只重启相关进程，不重建镜像。依赖和镜像定义变化使用 `rebuild`。

该文件落地前需要按正式任务流程补充验证，特别是三个服务是否都能读取同步后的 `/workspace/backend/src`，以及重启期间的健康检查能否正常恢复。

### 4.3 日常启动

在 `backend` 目录运行：

```powershell
cd backend
docker compose -f docker-compose.yml -f docker-compose.dev.yml watch
```

首次运行仍会构建并启动服务。此后修改 `backend/src` 下的 Python 文件时，Compose 会自动同步并重启对应容器；PostgreSQL 和命名卷不会因此重建。

如果服务已经由其他终端启动，可以使用：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml watch --no-up
```

按 `Ctrl+C` 停止 Watch。需要同时停止开发服务时，再显式执行：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

不要在仍有其他验证或开发流程使用同一 Compose 项目时直接执行 `down`。

## 5. 数据库迁移与配置变化

Alembic 迁移不应由 Watch 自动执行。`migrate` 是一次性服务，Schema 变化必须显式处理：

1. 停止当前 Watch。
2. 按当前任务的迁移流程重新构建相关镜像。
3. 显式运行 `migrate`。
4. 重新启动 `api`、`worker` 和 `scheduler`。
5. 重新进入 Watch，并运行受影响的 Focused/Fast 测试。

下列变化也可能需要 recreate 或 rebuild，不能依赖源码同步：

- `.env`、Compose environment 或 secret 文件路径；
- Python 依赖版本；
- Dockerfile、entrypoint 和系统依赖；
- Alembic 文件或数据库连接配置；
- 服务端口、卷或健康检查。

密钥和 Cookie 不得写入开发覆盖文件、命令历史、普通日志或本文档。

## 6. 推荐的日常开发流程

1. 在一个终端中启动后端 Compose Watch。
2. 等待 `postgres`、`api`、`worker` 和 `scheduler` 健康。
3. 在另一个终端中运行 `flutter run -d windows`。
4. 在客户端登录前设置页配置 `http://127.0.0.1:8000`。
5. 修改 Dart/UI 后使用 `r`；修改 Python 后等待 Compose 自动同步并重启。
6. 修改跨进程契约时，确认 API、worker 和 scheduler 均已重启并执行受影响测试。
7. TASK 完成前退出快速反馈循环，按 [统一实施与验证工作流](specs/001-sakuraplayer-v1/implementation-workflow.md) 执行完整差异自审、Fast 和 Final。

## 7. 常见问题

### Flutter 页面没有变化

先按 `r`。如果修改涉及初始化或状态创建，按 `R`。仍未生效时停止进程并重新运行 `flutter run -d windows`。

### API 已更新，但后台任务仍是旧行为

确认开发覆盖文件同时配置了 `api`、`worker` 和 `scheduler`。只重启 API 不足以覆盖后台任务。

### Python 修改后容器没有重启

检查 Watch 终端是否仍在运行、修改路径是否位于 `backend/src`，并执行 `docker compose watch --help` 确认当前 Compose 支持 Watch。

### 修改迁移后服务启动失败

停止 Watch，按任务规定显式重建并运行迁移。不要通过删除迁移、忽略 Schema 门禁或复用开发/生产数据来绕过问题。

### 热更新后是否可以直接提交任务

不可以。热更新只是开发反馈工具，不能代替测试、`git diff --check`、任务 Definition of Done、完整 Compose Final 或 Windows release 构建。
