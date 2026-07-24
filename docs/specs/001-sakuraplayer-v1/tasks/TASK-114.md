---
id: TASK-114
title: "115 缓存播放后端代码清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-113]
ac-mapping: []
imp-requirements: []
cross-boundary: false
external-dependency-risk: false
provides: [reviewed cloud cache playback files]
---

# TASK-114: 115 缓存播放后端代码清理

**功能描述**: 在 115 后端评审通过后执行纯卫生清理，保留所有协议、状态机、安全删除和公共签名行为。

## 验收条件

- [ ] 只清理 TASK-101 至 TASK-113 评审列出的文件。
- [ ] 删除 debug 日志/注释、临时 fixture、无用 import 和明显不可达代码，不改变状态转换。
- [ ] 运行 ruff format/check、类型检查、后端全量测试和 TASK-113 E2E。
- [ ] Cloud115 NOTICE、协议 fixture、错误码和真实测试 marker 保留。

## Definition of Ready

- [ ] TASK-113 reviewed/implemented 且 review 批准。
- [ ] 真实基线测试通过，清理文件清单完整。
- [ ] 无需要在 cleanup 阶段修复的逻辑缺陷。

## 技术上下文

- 使用 `specs-code-cleanup`；测试失败立即停止。
- 不升级 115 协议、不改重试/超时、不合并状态。
- 保留必要协议注释，尤其 UA、RSA/KDF 和删除证明。

## 实现文件（仅文件名）

**修改**:

- `backend/src/sakuraplayer/cloud_cache/` - 评审列出的文件。
- `backend/src/sakuraplayer/playback/` - 评审列出的文件。
- `backend/tests/` - 仅对应测试卫生。
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-114.md` - Cleanup Summary。

## 测试说明

- 扫描 `print(`、DEBUG/TEMP、未使用 import、短链/Cookie 误日志。
- 运行格式化、静态检查、全部单元/集成/E2E。
- 比较 OpenAPI 和状态转换表，确认无签名/功能变化。

## Definition of Done

- [ ] 仅卫生改动且所有测试重新通过。
- [ ] 无秘密或短链调试输出。
- [ ] 追加 Cleanup Summary 并完成任务。

**依赖**: TASK-113

**实现命令**:

`/developer-kit-specs:specs-code-cleanup --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-114.md"`
