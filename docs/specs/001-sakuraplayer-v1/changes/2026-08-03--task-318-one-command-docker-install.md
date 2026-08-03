# Change Specification: TASK-318 Linux 一键安全部署

**Type**: Delta
**Date**: 2026-08-03
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

SakuraPlayer v1.0.0 已提供 Docker Compose 与发布镜像，但 Linux 新用户仍需克隆仓库、复制 `.env`、手工生成五个 secret 并输入多条 Compose 命令。本变更增加不含 secret 的 Linux Docker 发布包和宿主机一键安装脚本；脚本自动完成强随机 secret、发布版 `.env`、Compose 拉取/启动和健康等待，同时保持既有启动配置、bootstrap、loopback 与日志安全不变量。

## MODIFIED

- AC-120、AC-133：启动级 secret 仍只通过文件或环境变量注入，格式、用途隔离和 bootstrap 生命周期不变；官方安装脚本可以在宿主机自动生成缺失的文件，但不得把值放入环境、参数、日志或响应。
- AC-123、AC-127：官方发布版 Compose 可由安装脚本统一拉取并启动；成功返回前必须通过 Compose `--wait` 健康条件，失败保留已有数据和已创建的 secret 供安全重试。
- AC-134：一键安装仍默认绑定 `127.0.0.1`，不得为了减少步骤自动改为局域网或公网监听。
- AC-140、AC-142：GitHub Release 在 Windows 与双 registry 路径之外还汇总 Linux Docker 部署包、SHA-256 和 artifact attestation；任一路径失败仍不得创建 Release。

## ADDED

- REQ-CHG-303 / AC-143：严格版本 tag 的 GitHub Release 必须包含 `SakuraPlayer-Docker-X.Y.Z.tar.gz` 与同名 `.sha256`；部署包只包含固定版本标记、Compose、无 secret 的环境模板、一键安装脚本、部署说明和许可证/第三方声明，不包含业务数据或凭据。
- REQ-CHG-304 / AC-144：Linux 一键安装脚本必须从任意工作目录解析部署包，检查 Docker/Compose/OpenSSL/flock，使用 `umask 077` 原子生成五个用途独立的规范 Base64URL secret，拒绝符号链接、非普通文件、非法既有 secret 和并发执行；重复运行必须复用并收紧权限而不覆盖任何有效 secret。脚本只输出阶段、访问地址与 bootstrap 文件路径，不输出 secret 值，并以完整 SemVer 镜像执行 `pull`、`config` 和 `up -d --no-build --wait`。

## Task Synchronization

新增独立 `TASK-318`，依赖 TASK-316 与 TASK-317，不改变 TASK-301..314 的 HarmonyOS 实施顺序。同步更新功能规格、运行配置/发布契约、任务总索引、追踪矩阵、README、后端部署说明和会话交接。

## Testing Strategy

用户明确批准本任务不执行 Focused/Fast/Final 三层验证和完整 Compose。替代验证覆盖：临时 Linux 目录中的首次安装与重复安装、精确 secret 格式/权限/唯一性、符号链接与非法既有文件拒绝、并发锁、stdout/stderr 泄漏、失败保留、Compose 参数捕获、发布包内容/哈希、workflow 权限/依赖/attestation 静态契约、真实 `docker compose config`、Shell 语法、完整差异和 secret 模式扫描。

## Rollback Plan

发布前可整体回退 TASK-318 提交；已有数据库与 secret 不由回滚脚本删除。某版本已发布的 Linux 部署包和 attestation 属于外部发布事实，不覆盖或删除，使用新的前向提交与递增版本修复。
