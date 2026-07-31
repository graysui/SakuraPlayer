---
id: TASK-212
title: "Windows 私有安装包与真实验收工具"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-201, TASK-202, TASK-203, TASK-204, TASK-205, TASK-206, TASK-207, TASK-208, TASK-209, TASK-210, TASK-211]
ac-mapping: [AC-005, AC-008, AC-009, AC-128, AC-129]
imp-requirements: [REQ-002, REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [Windows release packaging, explicit real115 test harness, license bundle]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-212: Windows 私有安装包与真实验收工具

**功能描述**: 建立 Windows release/私有安装包、许可证产物、默认离线自动测试和显式真实 115 验收 harness，为 TASK-213 提供可重复门禁。

**规格映射**: AC-005、AC-008、AC-009、AC-128、AC-129

## 外部依赖风险

- **依赖**: Windows runner/media_kit native libs 和真实 115 测试账号。
- **状态**: 真实凭据/样本只在受控环境提供。
- **缓解**: 默认 test 完全 fake，real suite 需要显式 flag/environment marker，安装包内保留许可证。

## 验收条件

- [x] Windows release 构建和私有安装包可生成，不包含公开商店流程；对应 AC-005、AC-008。
- [x] GPLv3、第三方声明和移植来源进入安装包；对应 AC-009。
- [x] 默认 analyze/test/integration 不访问真实 115/JavDB 写/AI；对应 AC-128。
- [x] 规格列出的解密、标签、状态机、签名、进度、字幕生命周期自动测试可从统一命令运行；对应 AC-129。

## Definition of Ready

- [x] TASK-201 至 TASK-211 实现并通过单元/Widget 测试。
- [x] real-115 所需 URL/凭据只由本地安全环境注入。
- [x] 安装包格式和签名策略适合私有分发。

## 技术上下文

- CI/default 不能读取真实 marker；real suite 输出脱敏证据。
- 发布不包含 Android/Web/macOS/Linux runner 或商店 metadata。
- native media_kit/libmpv DLL 完整随包。

## 实现文件（仅文件名）

**创建**:

- `windows/tool/build_private_release.ps1` - release/installer 构建。
- `windows/integration_test/fake_backend_flow_test.dart` - 默认完整 fake 流程。
- `windows/integration_test/real115_probe_test.dart` - 显式扫码/播放探针。
- `windows/tool/verify_release_contents.ps1` - 平台/许可证/native libs 扫描。
- `windows/test/release/license_bundle_test.dart` - GPLv3/NOTICE 检查。

## 测试说明

- 默认命令无真实环境变量时 real suite 明确 skip，不尝试网络。
- release 包含 exe/libmpv/字体/许可证，不含其他平台和 debug secret。
- real harness 能记录扫码、source/job/session ID 和状态码，但不记录 Cookie/磁力/完整 URL。

## Definition of Done

- [x] 私有安装包、默认测试和真实 harness 完成。
- [x] 发布内容/许可证扫描通过。
- [x] TASK-213 可使用同一产物执行 AC-130。

## 实现证据

- `build_private_release.ps1` 真实执行 Windows release build，生成带当前用户安装/卸载脚本、包内 `SHA256SUMS.txt`、ZIP sidecar SHA-256 和可选 CurrentUser Authenticode 的私有 ZIP；`verify_release_contents.ps1` 拒绝缺失 exe、Flutter DLL、`libmpv-2.dll`、AOT/ICU、Flutter `NOTICES.Z`、GPL/Windows NOTICE/项目移植来源 NOTICE 或哈希不完整的产物。
- `fake_backend_flow_test.dart` 在 Windows runner 上以 Riverpod Fake 启动媒体库与排行榜，默认入口不引用 real115 marker；`real115_probe_test.dart` 缺少 marker 时明确 skip 且不尝试网络，显式运行时仅从本地环境读取后端/账号/样本，输出脱敏 stage/status/source/job/session 证据并调用受管 cleanup。
- `run_default_tests.ps1` 使用冻结 Python 3.10.16 `sakuraplayer-test` 镜像只读挂载运行 AC-129 算法清单，再运行 Flutter analyze、完整 unit/widget 和 Windows Fake integration；Fast 为后端 173 项、Flutter 206 项、Windows integration 1 项通过。
- Final：PowerShell AST 与 5 项发布契约通过；真实 `flutter build windows --release` 成功，34 文件内容/许可证/native/hash 扫描通过并生成 `SakuraPlayer-Windows-1.0.0-1.zip`。未执行 TASK-213 真实账号/AC-130 门禁。

**依赖**: TASK-201..TASK-211

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-212.md"`
