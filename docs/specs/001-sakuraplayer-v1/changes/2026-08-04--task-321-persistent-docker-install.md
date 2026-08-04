# Change Specification: TASK-321 Linux Docker 持久化安装与网络选择

**Type**: Delta
**Date**: 2026-08-04
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-320 的远程引导器在临时解压目录中调用 `install.sh`，导致 `.env`、`secrets/` 和 bootstrap token 在脚本结束时随临时目录删除。本变更把发布文件和运行配置落到执行命令时的当前目录，并让首次交互式一键安装选择 Docker 发布 IPv4 地址和 API 端口；没有 TTY 时保持可自动运行的 loopback 默认值。

## MODIFIED

- AC-143、AC-144、AC-147：远程引导器的下载、解压和校验仍只使用临时目录，但安装器必须在持久目标目录内运行；已有 `.env` 和有效 secret 不得被覆盖。若检测到上一版引导器留下的同项目运行容器，脚本应尽力恢复容器内的五项 secret；无法完整恢复时必须停止，避免新 secret 与既有数据库混用。
- AC-134：默认仍为 `127.0.0.1:8000`；首次交互安装可显式设置合法 IPv4 和 `1..65535` 端口，不接受 `0.0.0.0`。

## ADDED

- REQ-CHG-307 / AC-148：Linux `install-latest.sh` 默认以执行命令时的当前目录作为持久安装目录，可用 `SAKURAPLAYER_INSTALL_DIR` 指定已有真实目录；首次安装从 `/dev/tty` 询问 `SAKURAPLAYER_PUBLISH_HOST` 和 `SAKURAPLAYER_API_PORT`，直接回车或无 TTY 使用 `127.0.0.1:8000`，已有 `.env` 保持原配置。临时目录退出时必须清理，输出不得包含任何 secret。

## Task Synchronization

新增独立 `TASK-321`，依赖 TASK-320；同步更新功能规格、运行配置契约、GitHub 发布契约、任务索引、追踪矩阵、README、后端部署说明和会话交接。TASK-320 的单命令入口与发布校验事实不回写覆盖。

## Testing Strategy

定向覆盖当前目录持久化、临时目录清理、默认与指定网络配置、非法 host/port、已有 `.env` 保留、已有容器 secret 恢复路径，以及发布包、workflow 和文档契约。执行 Bash 语法、Compose config、Ruff、`git diff --check` 和 secret 模式审计；默认测试不访问真实 115、真实业务服务或付费 AI。

## Rollback Plan

发布前可回退 TASK-321 提交；已有 `.env`、secret、Docker volumes 和数据库不由回滚动作删除。若新引导器不可用，用户仍可使用已发布归档中的 `./install.sh` 或手动 Compose 路径。
