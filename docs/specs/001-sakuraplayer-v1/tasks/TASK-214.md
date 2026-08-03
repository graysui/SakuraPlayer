---
id: TASK-214
title: "Windows 客户端代码清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
reviewed_date: 2026-08-03
completed_date: 2026-08-03
cleanup_date: 2026-08-03
dependencies: [TASK-213, TASK-215, TASK-216, TASK-217, TASK-218, TASK-219, TASK-220, TASK-221, TASK-222, TASK-223, TASK-226, TASK-227]
ac-mapping: []
imp-requirements: []
cross-boundary: false
external-dependency-risk: false
provides: [reviewed Windows client files]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-214: Windows 客户端代码清理

**功能描述**: Windows E2E 评审后执行 Dart/Flutter 卫生清理，不改变导航、状态、播放器、固定 UA 或平台构建行为。

## 验收条件

- [x] 只处理 TASK-201 至 TASK-213 及其后置运行修复任务 review 列出的 Windows 文件。
- [x] 移除 debugPrint/console、临时注释、无用 import/asset 和明显死代码。
- [x] 运行 `dart format`、`flutter analyze`、`flutter test`、integration test 和 Windows release build。
- [x] 不新增其他平台、不升级依赖、不改变播放器签名/seek 行为。

## Definition of Ready

- [x] 所有依赖任务 completed，AC-130 证据已批准。
- [x] 当前 Flutter 测试和 release build 通过。
- [x] 所有清理文件在 [TASK-214 Review Report](TASK-214--review.md) 中。

## 技术上下文

- 使用 specs-code-cleanup，测试失败停止。
- Dart import 顺序、格式由官方 formatter；生成代码不手改。
- 保留 GPLv3/NOTICE 和必要的 media_kit/UA 注释。

## 实现文件（仅文件名）

**修改**:

- `windows/lib/` - review 列出的 Dart 文件。
- `windows/test/`、`windows/integration_test/` - 测试卫生。
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-214.md` - Cleanup Summary。

## 测试说明

- 扫描 `print(`、`debugPrint`、TODO remove、未使用资源和非 Windows 平台引用。
- 完整 format/analyze/test/integration/release 重跑。
- 比较 OpenAPI DTO、固定 UA 和路由表，确认无行为/签名变化。

## Definition of Done

- [x] 仅卫生改动，全部验证通过。
- [x] 安装包仍含许可证且无 debug secret。
- [x] 追加 Cleanup Summary 并完成任务。

## Cleanup Summary

- 从 `508643ec4332aa3563f301d41164d1637abbce6a..7d377d1` 重建 131 个 Windows 历史文件，并在 [TASK-214 Review Report](TASK-214--review.md) 中固定批准清单；生成代码、原生 runner、依赖锁、许可证、发布工具和测试证据均未做无依据修改。
- 唯一产品卫生改动位于 `windows/lib/app/composition_root.dart`：移除两处固定 `debugPrint`，保留 best-effort 字幕缓存清理的异常吞吐、异步时序与后续重试语义。真实 115 probe 的脱敏结构化输出按契约保留。
- 清理前后固定 UA、路由、API/DTO、播放器、seek、依赖与 Windows runner 文件无差异；生产 debug 输出、有效 TODO/FIXME/HACK、敏感模式和 `git diff --check` 均为 0。
- Focused 通过目标文件格式、analyze 与 15 项应用组合/路由测试；Fast 通过 97 文件格式、analyze 零问题、233 项 Flutter 测试、4 项 Fake 用户旅程和 1 项原生 Fake smoke。
- Final 通过 Windows Release 构建；私有发布工具验证 34 个文件，覆盖 exe、Flutter/libmpv、AOT/ICU、GPLv3/NOTICE、安装脚本、完整 SHA-256 清单，以及其他平台、PDB、密钥和 debug 日志拒绝。

**完成日期**: 2026-08-03

**依赖**: TASK-213, TASK-215, TASK-216, TASK-217, TASK-218, TASK-219, TASK-220, TASK-221, TASK-222, TASK-223, TASK-226, TASK-227

**实现命令**:

`/developer-kit-specs:specs-code-cleanup --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-214.md"`
