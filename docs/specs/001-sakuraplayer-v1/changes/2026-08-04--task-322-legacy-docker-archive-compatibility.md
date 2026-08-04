# Change Specification: TASK-322 旧版 Linux Docker 归档兼容

**Type**: Delta
**Date**: 2026-08-04
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

`v1.0.1` 已发布的 Linux Docker 归档是在远程引导器进入发布包之前生成的，包含 `install.sh` 但不包含 `install-latest.sh`。TASK-321 将后者加入持久化发布文件白名单后，直接执行旧 Release 会在 Compose 启动前误报归档布局错误。本变更让远程引导器兼容缺少自身副本的旧归档，同时继续严格校验实际安装所需文件。

## MODIFIED

- AC-147、AC-148：`install-latest.sh` 在检查旧归档时将 `install-latest.sh` 视为向后兼容的可选发布文件；`docker-compose.yml`、`.env.example`、`.release-version`、`install.sh`、部署说明和许可证文件仍必须存在。新构建的归档继续包含完整白名单。

## Task Synchronization

新增独立 `TASK-322`，依赖 TASK-321；同步更新 GitHub 发布契约、任务索引、追踪矩阵、测试和会话交接。已发布的 `v1.0.1` 资产不回写修改。

## Testing Strategy

增加旧归档缺少 `install-latest.sh` 的远程引导回归测试，并运行 Linux 安装器、发布包、workflow、部署文档、Ruff、Bash 语法、Compose config、差异和 secret 扫描。
