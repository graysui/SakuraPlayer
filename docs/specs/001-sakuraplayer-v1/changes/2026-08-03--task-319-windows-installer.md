# Change Specification: TASK-319 Windows 单文件安装器

**Type**: Delta
**Date**: 2026-08-03
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

当前 Windows Release 只提供包含 Flutter 运行时目录的 ZIP 和当前用户 PowerShell 安装脚本。新增一个由固定版本 Inno Setup 生成的单文件安装器 EXE，安装器内部携带同一份经过校验的 release bundle，默认安装到当前用户目录，不需要管理员权限；既有 ZIP 继续发布，作为可审计和手动部署选项。

## ADDED

- **REQ-CHG-305 / AC-145**：正式 GitHub Release 除 Windows ZIP 外必须提供 `SakuraPlayer-Windows-X.Y.Z-B-Setup.exe` 及同名 `.sha256`；安装器必须来自同一份 Flutter x64 release bundle，包含应用 EXE、Flutter/native DLL、AOT/ICU 数据、许可证和第三方声明，不得产生缺失运行库的伪单文件包。
- **REQ-CHG-306 / AC-146**：Windows 安装器必须由固定版本 Inno Setup 在 `windows-2022` 上构建，默认使用当前用户安装目录且不要求管理员权限；安装器和校验文件生成 GitHub artifact attestation，公共构建继续明确为 unsigned，Authenticode 只能通过显式签名配置启用。

## MODIFIED

- AC-138、AC-140、AC-142：Windows ZIP 发布、Release 原子创建和供应链证明继续有效，并扩展为同时汇总安装器 EXE 及其 SHA-256；ZIP 不被替换或删除。
- README 和 Windows 发布说明：下载路径优先展示安装器 EXE，同时保留 ZIP 手动安装路径，并说明安装器不是 Flutter 单二进制运行文件。

## Task Synchronization

新增独立 `TASK-319`，依赖 TASK-212、TASK-316、TASK-317；不改变 TASK-318 的 Linux 部署边界和 TASK-301..314 的 HarmonyOS 顺序。同步更新 Windows 发布契约、功能规格、任务索引、追踪矩阵、README、Windows README 和会话交接。

## Testing Strategy

- Focused/Fast：版本工具、workflow 资产传递、Action SHA/权限、Inno 配置静态约束、bundle 白名单和 SHA-256 契约测试。
- Final：在 Windows 上运行既有 release bundle 构建，使用固定 Inno Setup 编译单文件安装器，检查安装器与 sidecar SHA-256、文件名、无凭据和发布资产；不运行后端 Compose 或完整后端测试矩阵。

## Rollback Plan

正式 tag 发布前可整体回退 TASK-319 提交。已发布的安装器、ZIP 和 attestation 属于不可变外部事实，修复使用新的递增版本 tag，不覆盖既有资产。
