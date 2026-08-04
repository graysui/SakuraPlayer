# Change Specification: TASK-323 Linux Docker 数据目录与配置兼容

## 背景

TASK-321 修复了一键脚本将 `.env` 和 secret 留在临时目录的问题，但已发布的旧 Docker 归档仍使用 Docker named volume，且旧数据库中的 PostgreSQL 角色密码可能与新生成的宿主 secret 不一致。现场表现为配置输入没有写回 `.env`、数据继续位于 Docker 系统目录，以及 `migrate` 因数据库密码认证失败而无法健康启动。

## 变更

- REQ-CHG-308 / AC-148：只有首次安装且没有 `.env` 时才通过 `/dev/tty` 询问 host/port；输入值写入执行目录的 `.env`，已有 `.env` 不再询问、不覆盖。
- REQ-CHG-309 / AC-149：新 Compose 使用安装目录下的四个 `data/` bind mount。远程引导器遇到旧 `sakuraplayer_*` named volume 时，停止旧项目容器、复制数据到对应目录并保留旧卷；复制过程使用 root 权限避免 NAS 宿主目录初始权限阻断迁移。
- REQ-CHG-310 / AC-149：安装启动 PostgreSQL 后，以当前 `secrets/postgres_password.txt` 同步既有数据库角色密码，再执行迁移和其余服务健康等待，兼容旧数据库与新 secret 的组合。
- 发布说明、README、架构、运行配置契约、任务索引、追踪矩阵和交接文档必须说明实际 `data/` 路径与旧 named volume 的迁移边界。

## 范围与安全

- 不删除、不覆盖原 Docker named volume；迁移失败必须在 Compose 完整启动前报错。
- 不输出 secret 值、数据库 DSN 或 SQL 内容；只输出阶段和普通路径。
- 不改变默认 `127.0.0.1:8000`、五个 secret 的生成规则、SHA-256 发布资产或手动安装路径。
- 本变更只处理 Linux Docker 部署，不改变 Windows、HarmonyOS 或业务 API 契约。

## 回滚

发布前可回退 TASK-323 提交，但回滚动作不得删除安装目录 `data/`、`.env`、`secrets/` 或旧 named volume。若安装器失败，保留现场供操作者检查，不自动清理业务数据。

## 验证边界

本次回归运行 `backend/tests/start/test_linux_installer.py`，结果为 `18 passed`；未运行完整 Compose。用户仍需在飞牛 NAS 上验证实际安装、Compose 健康状态、`.env` 内容和数据目录位置。
