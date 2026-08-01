---
id: TASK-214
title: "Windows 客户端代码清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-213, TASK-215, TASK-216, TASK-217, TASK-218]
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

- [ ] 只处理 TASK-201 至 TASK-213 review 列出的文件。
- [ ] 移除 debugPrint/console、临时注释、无用 import/asset 和明显死代码。
- [ ] 运行 `dart format`、`flutter analyze`、`flutter test`、integration test 和 Windows release build。
- [ ] 不新增其他平台、不升级依赖、不改变播放器签名/seek 行为。

## Definition of Ready

- [ ] TASK-213 reviewed/implemented，AC-130 证据已批准。
- [ ] 当前 Flutter 测试和 release build 通过。
- [ ] 所有清理文件在 review report 中。

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

- [ ] 仅卫生改动，全部验证通过。
- [ ] 安装包仍含许可证且无 debug secret。
- [ ] 追加 Cleanup Summary 并完成任务。

**依赖**: TASK-213, TASK-215, TASK-216, TASK-217, TASK-218

**实现命令**:

`/developer-kit-specs:specs-code-cleanup --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-214.md"`
