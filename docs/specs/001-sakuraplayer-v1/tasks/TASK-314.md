---
id: TASK-314
title: "HarmonyOS 客户端代码清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-313]
ac-mapping: []
imp-requirements: []
cross-boundary: false
external-dependency-risk: false
provides: [reviewed HarmonyOS client files]
---

# TASK-314: HarmonyOS 客户端代码清理

**功能描述**: HarmonyOS E2E 与真机门禁通过后执行 ArkTS/ArkUI/Hvigor 卫生清理，不改变导航、状态、AVPlayer、固定 UA、字幕或签名行为。

## 验收条件

- [ ] 只处理 TASK-301 至 TASK-313 review 列出的文件。
- [ ] 移除 console/临时 HiLog、临时注释、无用 import/resource 和明显死代码，保留必要诊断日志。
- [ ] 运行 ArkTS strict check、Hvigor 单元测试、Hypium/UiTest、release HAP 构建和内容检查。
- [ ] 不升级 SDK/依赖，不新增推测的 Media Kit API，不改变网络头、路由、序列化和播放行为。

## Definition of Ready

- [ ] TASK-313 reviewed/implemented，TASK-312 的 AC-131 真机证据仍有效。
- [ ] 当前 strict check、测试和签名 release HAP 构建通过。
- [ ] 所有清理文件已列入 review report，ArkGuard nameCache 可用。

## 技术上下文

- 使用 specs-code-cleanup，任何测试或签名内容检查失败都停止。
- 由 ArkTS formatter/linter 处理格式和 import；生成文件、SDK 声明和签名材料不手改。
- 保留 GPLv3/NOTICE、固定 UA、AVPlayer 生命周期和外部字幕能力边界的必要说明。

## 实现文件（仅文件名）

**修改**:

- `harmony/entry/src/main/ets/` - review 列出的 ArkTS 文件。
- `harmony/entry/src/test/`、`harmony/entry/src/ohosTest/` - 测试卫生。
- `harmony/entry/src/main/resources/` - review 确认未使用的资源。
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-314.md` - Cleanup Summary。

## 测试说明

- 扫描 `console.`、临时 HiLog、TODO remove、未使用资源、动态类型逃逸和非 API 24 引用。
- 完整 strict check、unit、Hypium/UiTest、release HAP、ArkGuard/nameCache 和 HAP 内容检查重跑。
- 比较 OpenAPI DTO、固定 UA、NavPathStack 路由、Asset Store 键和 AVPlayer 状态映射，确认无行为或签名变化。

## Definition of Done

- [ ] 只有卫生改动，全部验证通过。
- [ ] 签名 HAP 可侧载，含许可证且不含 debug secret、私有日志或签名材料。
- [ ] 追加 Cleanup Summary 并完成任务。

**依赖**: TASK-313

**实现命令**:

`/developer-kit-specs:specs-code-cleanup --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-314.md"`
