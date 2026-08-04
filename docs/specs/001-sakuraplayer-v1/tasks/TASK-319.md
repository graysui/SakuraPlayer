---
id: TASK-319
title: "Windows 单文件安装器 EXE 与 GitHub 发布资产"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-212, TASK-316, TASK-317]
ac-mapping: [AC-138, AC-140, AC-142, AC-145, AC-146]
imp-requirements: [REQ-028, REQ-CHG-305, REQ-CHG-306]
cross-boundary: false
external-dependency-risk: false
provides: [Windows single-file installer EXE, installer checksum, installer attestation]
---

# TASK-319: Windows 单文件安装器 EXE 与 GitHub 发布资产

**功能描述**: 在保留既有 Windows x64 ZIP 发布物的基础上，使用固定版本 Inno Setup 从同一份 Flutter release bundle 生成当前用户单文件安装器 EXE，并由 GitHub Release 同时发布安装器、校验文件和供应链证明。

## 验收条件

- [x] Inno Setup 配置只打包已通过既有 release bundle 校验的 Flutter x64 文件、许可证和第三方声明。
- [x] 安装器默认安装到 `%LOCALAPPDATA%\Programs\SakuraPlayer`，不要求管理员权限，不覆盖应用私有数据目录。
- [x] 安装器文件名为 `SakuraPlayer-Windows-X.Y.Z-B-Setup.exe`，并生成同名 `.sha256`；ZIP 和 ZIP 校验文件继续发布。
- [x] tag Release 只有在质量、Windows ZIP/安装器、Linux 部署包和 Docker 路径全部成功后创建；安装器资产生成 GitHub artifact attestation。
- [x] 公共构建保持 unsigned 事实，README 和 Windows README 清楚区分“单文件安装器”与“单二进制 Flutter EXE”。

## Definition of Ready

- [x] TASK-212、TASK-316、TASK-317 completed，Windows release bundle、版本校验和 GitHub Release 已存在。
- [x] 当前 GitHub 发布契约已明确 ZIP、Linux 部署包、Docker 镜像和 attestation 规则。
- [x] 用户确认采用推荐的 Windows 单文件安装器方案，并允许保留 ZIP。
- [x] 本任务不运行后端三层 Compose 验证；Windows 发布产物使用任务内定向门禁验证。

## 实现文件（仅文件名）

**新增**:

- `windows/tool/package/SakuraPlayer.iss`
- `windows/tool/build_windows_installer.ps1`
- `docs/specs/001-sakuraplayer-v1/changes/2026-08-03--task-319-windows-installer.md`
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-319.md`

**修改**:

- `.github/workflows/release.yml`
- `tools/release/validate_version.py`
- `backend/tests/start/test_release_workflows.py`
- `docs/specs/001-sakuraplayer-v1/contracts/github-release.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
- `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1--tasks.md`
- `docs/specs/001-sakuraplayer-v1/traceability-matrix.md`
- `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`
- `README.md`
- `windows/README.md`

## 验证例外

用户明确批准本任务不运行完整后端 Compose。仍执行当前任务的 Focused/Fast/Final Windows 发布门禁：版本与 workflow 契约测试、PowerShell/Inno 静态检查、实际 Windows release bundle 和 Inno installer 构建、产物/校验/许可证审计、完整差异审计、`git diff --check` 和 secret 扫描。

## Definition of Done

- [x] 变更规格、功能规格、发布契约、任务索引和追踪映射一致。
- [x] 安装器脚本、版本输出、workflow 上传/attestation 和 Release 资产依赖实现完成。
- [x] 安装器实际可由当前 Windows runner 工具链构建，并通过 sidecar SHA-256 与内容检查。
- [x] 发布文档明确安装器、ZIP、未签名和单二进制边界。
- [x] 用户批准的 Windows 定向验证、完整差异审计和 `git diff --check` 通过。
- [x] 任务状态与交接在同一中文提交中更新。

**依赖**: TASK-212, TASK-316, TASK-317
