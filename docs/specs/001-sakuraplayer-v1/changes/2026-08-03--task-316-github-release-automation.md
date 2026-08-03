# Change Specification: TASK-316 GitHub 自动发布

**Type**: Delta
**Date**: 2026-08-03
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

SakuraPlayer 已成为公开 GitHub 仓库，但尚无自动验证、版本 tag、Windows Release 或后端容器镜像。本变更建立两条 GitHub Actions：pull request 与 `main` 只执行无外部凭据的离线验证；严格 `vX.Y.Z` tag 在版本一致性通过后构建 Windows x64 私有 ZIP、把一个供 API/migrate/worker/scheduler 共用的 Linux amd64 后端 runtime 镜像同时发布到 GHCR 与 Docker Hub、生成 SHA-256 与 artifact attestations，并创建 GitHub Release。

## MODIFIED

- AC-005、AC-008：第一阶段 Windows 私有安装包可通过 GitHub Release 直接分发，但仍不是公开应用商店安装包；发布产物继续使用 TASK-212 的当前用户安装/卸载与内容验证流程。
- AC-009：Windows ZIP、外层校验文件和后端镜像必须保留 GPL-3.0-only、第三方声明与复用来源；GitHub Release 不改变既有许可证责任。
- AC-123：API、migrate、worker、scheduler 使用同一个后端 runtime 镜像和不同 command；本地 Compose 仍支持源码构建，也可通过显式镜像变量拉取 GHCR 或 Docker Hub 版本。
- AC-128：GitHub 默认验证不得访问真实 115、JavDB/DMM/GFriends 或付费 AI，也不得要求仓库业务 secret。

## ADDED

- REQ-CHG-296 / AC-136：pull request 与 `main` push 必须运行后端自包含测试/静态检查、Docker runtime 构建和 Windows analyze/test/release build；失败不得发布。
- REQ-CHG-297 / AC-137：正式发布只由严格 `vX.Y.Z` tag 触发，tag 版本必须等于 `windows/pubspec.yaml` 的 SemVer 主版本；Flutter `+build` 只进入 Windows 资产名。
- REQ-CHG-298 / AC-138：Windows 发布资产固定为 `SakuraPlayer-Windows-X.Y.Z-B.zip` 及同名 `.sha256`；ZIP 必须由既有私有 Release 脚本生成并通过包内文件、许可证和 SHA-256 校验。
- REQ-CHG-299 / AC-139：同一次构建把 Linux amd64 runtime 镜像推送到 `ghcr.io/graysui/sakuraplayer-backend` 和 `docker.io/graysui/sakuraplayer-backend`，Python 基础镜像固定 digest，两处至少包含完整版本、major.minor、major、`latest` 和 Git SHA 标签并指向同一 digest；四个后端进程复用该 digest。
- REQ-CHG-300 / AC-140：tag 工作流成功后创建 GitHub Release，上传 Windows ZIP 和 `.sha256`，并保留 GitHub 自动生成的变更说明；任一构建或证明失败时不得创建 Release。
- REQ-CHG-301 / AC-141：工作流默认权限为只读，发布 job 仅显式申请所需的 `contents: write`、`packages: write`、`id-token: write`、`attestations: write`；第三方 Action 固定完整 commit SHA；GitHub 操作不得依赖个人 PAT，Docker Hub 只允许读取专用仓库 Secret `DOCKERHUB_TOKEN`，普通验证不得读取它或任何业务 secret。
- REQ-CHG-302 / AC-142：Windows ZIP/校验文件与 GHCR、Docker Hub 镜像 digest 必须生成 GitHub artifact attestation；发布文档说明镜像 digest/版本选择和 Windows 未签名状态，不把 attestations 描述为 Authenticode。

## Task Synchronization

新增独立 `TASK-316`，依赖 TASK-001、TASK-212、TASK-214、TASK-315，不改变 TASK-301..314 的 HarmonyOS 实施顺序。同步更新功能规格、发布契约、任务总索引、追踪矩阵、README 和会话交接。

## Testing Strategy

- Focused：版本解析、非法 tag、版本不一致、工作流触发器、权限、Action SHA、资产名、GHCR/Docker Hub 双仓库标签、专用 Secret 边界和 Compose 共用镜像的静态契约测试。
- Fast：后端发布契约测试、Docker Compose config、后端 runtime 镜像构建、Flutter analyze/test 和 Windows Release 构建/包内容验证。
- Final：完整后端 Compose 门禁、Windows Release 重建、完整差异/秘密审计；提交推送后使用 GitHub CLI 确认远程 verify 工作流绿色且 release 工作流被 GitHub 正确识别。

## Rollback Plan

正式 tag 发布前可整体回退 TASK-316 提交。已有 Release、tag、GHCR/Docker Hub 包或 attestation 属于外部不可变发布事实，不通过删除或覆盖回滚；需要修复时使用新的前向提交和递增版本 tag。
