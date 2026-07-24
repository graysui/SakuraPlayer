---
id: TASK-106
title: "确定性失败与来源拒绝集成"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-104]
ac-mapping: [AC-036]
imp-requirements: [REQ-007]
cross-boundary: false
external-dependency-risk: true
provides: [deterministic 115 failure classifier, SourceRejectionPort integration]
---

# TASK-106: 确定性失败与来源拒绝集成

**功能描述**: 区分 115 确定性失效/违规/无法离线和临时错误，前者通过资源上下文公开端口擦除磁力并写永久拒绝标记。

**规格映射**: AC-036

## 外部依赖风险

- **依赖**: 115 失败 errno/状态文案。
- **状态**: 非官方错误集合可变化。
- **缓解**: 只有明确白名单证据触发永久拒绝；未知/网络/限流错误不得拒绝来源。

## 验收条件

- [ ] 仅明确失效、违规或无法离线触发来源拒绝；对应 AC-036。
- [ ] 拒绝调用只传 website、tid 和稳定 reason，不传磁力；对应 AC-036。
- [ ] 拒绝完成后活动来源磁力清空、后续 AVdb 同步不重导；对应 AC-036。
- [ ] 临时 unavailable、限流和提交不确定只标缓存任务失败/待诊断，不写永久拒绝。

## Definition of Ready

- [ ] TASK-104 能产生标准化 115 错误，TASK-006 SourceRejectionPort 可用。
- [ ] 确定性错误白名单由真实 fixture 证明。
- [ ] 跨上下文只允许端口调用，不直接 import 资源 repository。

## 技术上下文

- Cache 上下文是 rejection 客户，Resources 上下文是 owner。
- 端口调用和 CacheJob failed 事件需要幂等；重复错误不重复泄漏/写入。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/failure_classifier.py` - 确定性/临时分类。
- `backend/src/sakuraplayer/cloud_cache/source_rejection_client.py` - 端口调用协调。
- `backend/tests/unit/cloud_cache/test_failure_classifier.py` - errno/状态白名单。
- `backend/tests/integration/cloud_cache/test_source_rejection.py` - 端到端清磁力和再导入阻止。

## 测试说明

**单元测试**:

- 失效/违规/无法离线命中；网络、429、5xx、未知 errno、提交不确定不命中。
- error payload/日志不出现磁力或上游正文。

**集成测试**:

- 确定性失败后验证 CacheJob failed、SourceRejection 存在、source magnet null、增量/全量跳过。
- 重复处理同一失败幂等，临时失败保留来源可手动再次播放。

## Definition of Done

- [ ] 分类器和端口集成完成。
- [ ] 永久拒绝只由明确证据触发。
- [ ] 不含磁力的持久/日志扫描通过。

**依赖**: TASK-104

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-106.md"`
