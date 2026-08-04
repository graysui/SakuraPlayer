# Change Specification: TASK-320 Linux 单命令 Docker 引导

**Type**: Delta
**Date**: 2026-08-04
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-318 已提供固定版本 Linux Docker 发布包和本地 `install.sh`，但新用户仍需打开 Release 页面、下载归档、解压并执行校验命令。此变更增加远程引导脚本：用户复制一条 `curl | bash` 命令后，脚本自动解析最新正式版本、下载对应 Docker 发布包、临时解压并调用包内安装器；不要求用户手动下载 Release、解压或执行 SHA256 校验。既有 SHA256 资产、attestation、本地发布包安装器和手动 Compose 高级路径继续保留。

## MODIFIED

- AC-143、AC-144：Linux 发布包继续提供固定版本归档、SHA256 和完整本地安装器安全语义；推荐入口额外提供自动下载和启动的远程引导模式，不改变 secret、loopback、幂等、权限和健康等待规则。
- AC-140、AC-142：发布流程继续生成 SHA256 与 artifact attestation；它们不再是推荐单命令执行的用户前置步骤。

## ADDED

- REQ-CHG-305 / AC-147：官方 Linux 新手入口必须支持一条命令自动获取 GitHub Releases 最新正式 `vX.Y.Z` 资产，按固定归档命名下载并在临时目录调用包内 `install.sh`；非法版本、下载失败、归档布局异常必须在 Compose 启动前失败，临时目录必须清理，输出不得包含 secret。该入口不执行用户端 SHA256 校验，也不得要求用户手动下载或解压 Release。

## Task Synchronization

新增 `TASK-320`，依赖已完成的 TASK-318、TASK-319；同步更新功能规格、GitHub 发布契约、任务总索引、追踪矩阵、README、后端部署说明、发布归档白名单和会话交接。TASK-318 的已完成事实和原有资产不回写覆盖。

## Testing Strategy

定向覆盖远程引导器的最新版本重定向、固定归档 URL、归档解压、包内安装器调用、非法版本拒绝、临时目录清理和 SHA256 不调用；同时运行 Docker 归档白名单/可重复性测试、发布 workflow 契约、Shell 语法、必要的 Compose config、完整差异、`git diff --check` 和 secret 扫描。默认测试不访问真实业务服务或真实 115。

## Rollback Plan

发布前可整体回退 TASK-320 提交；已有数据库、secret 和已发布资产不由回滚脚本删除。若远程引导不可用，用户仍可使用既有 Release 资产的 SHA256、本地 `install.sh` 或手动 Compose 路径。
