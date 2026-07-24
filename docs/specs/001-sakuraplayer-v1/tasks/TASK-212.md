---
id: TASK-212
title: "Windows 私有安装包与真实验收工具"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-201, TASK-202, TASK-203, TASK-204, TASK-205, TASK-206, TASK-207, TASK-208, TASK-209, TASK-210, TASK-211]
ac-mapping: [AC-005, AC-008, AC-009, AC-128, AC-129]
imp-requirements: [REQ-002, REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [Windows release packaging, explicit real115 test harness, license bundle]
---

# TASK-212: Windows 私有安装包与真实验收工具

**功能描述**: 建立 Windows release/私有安装包、许可证产物、默认离线自动测试和显式真实 115 验收 harness，为 TASK-213 提供可重复门禁。

**规格映射**: AC-005、AC-008、AC-009、AC-128、AC-129

## 外部依赖风险

- **依赖**: Windows runner/media_kit native libs 和真实 115 测试账号。
- **状态**: 真实凭据/样本只在受控环境提供。
- **缓解**: 默认 test 完全 fake，real suite 需要显式 flag/environment marker，安装包内保留许可证。

## 验收条件

- [ ] Windows release 构建和私有安装包可生成，不包含公开商店流程；对应 AC-005、AC-008。
- [ ] GPLv3、第三方声明和移植来源进入安装包；对应 AC-009。
- [ ] 默认 analyze/test/integration 不访问真实 115/JavDB 写/AI；对应 AC-128。
- [ ] 规格列出的解密、标签、状态机、签名、进度、字幕生命周期自动测试可从统一命令运行；对应 AC-129。

## Definition of Ready

- [ ] TASK-201 至 TASK-211 实现并通过单元/Widget 测试。
- [ ] real-115 所需 URL/凭据只由本地安全环境注入。
- [ ] 安装包格式和签名策略适合私有分发。

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

- [ ] 私有安装包、默认测试和真实 harness 完成。
- [ ] 发布内容/许可证扫描通过。
- [ ] TASK-213 可使用同一产物执行 AC-130。

**依赖**: TASK-201..TASK-211

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-212.md"`
