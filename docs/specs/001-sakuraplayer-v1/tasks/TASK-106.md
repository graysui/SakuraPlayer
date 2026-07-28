---
id: TASK-106
title: "确定性失败与来源拒绝集成"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-104]
ac-mapping: [AC-036]
imp-requirements: [REQ-007]
cross-boundary: false
external-dependency-risk: true
provides: [deterministic 115 failure classifier, SourceRejectionPort integration]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-106: 确定性失败与来源拒绝集成

**功能描述**: 区分 115 确定性失效/违规/无法离线和临时错误，前者通过资源上下文公开端口擦除磁力并写永久拒绝标记。

**规格映射**: AC-036

## 外部依赖风险

- **依赖**: 115 失败 errno/状态文案。
- **状态**: 固定 revision 的普通失败状态没有永久原因字段；非官方错误集合仍可能变化。
- **缓解**: 初始白名单只接受提交端点固定 not-found errno 与远端文件 blocked 标记；未知、
  普通下载失败、网络、限流及协议错误不得拒绝来源。详见
  [TASK-106 来源拒绝确定性边界](../changes/2026-07-28--task-106-source-rejection-determinism.md)。

## 验收条件

- [x] 仅明确失效、违规或无法离线触发来源拒绝；对应 AC-036。
- [x] 拒绝调用只传 website、tid 和稳定 reason，不传磁力；对应 AC-036。
- [x] 拒绝完成后活动来源磁力清空、后续 AVdb 同步不重导；对应 AC-036。
- [x] 临时 unavailable、限流和提交不确定只标缓存任务失败/待诊断，不写永久拒绝。

## Definition of Ready

- [x] TASK-104 能产生标准化 115 错误，TASK-006 SourceRejectionPort 可用。
- [x] 固定上游 revision 的脱敏历史响应证明初始白名单；普通 remote failed 明确不在白名单。
- [x] 跨上下文只允许端口调用，不直接 import 资源 repository。

## 技术上下文

- Cache 上下文是 rejection 客户，Resources 上下文是 owner。
- 端口调用和 CacheJob failed 事件需要幂等；重复错误不重复泄漏/写入。
- 确定性处理必须先幂等拒绝，再在 claim-fenced CacheJob 事务写 failed 与唯一事件；两步间
  崩溃由 claim expiry 重领收敛。

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

- [x] 分类器和端口集成完成。
- [x] 永久拒绝只由明确证据触发。
- [x] 不含磁力的持久/日志扫描通过。

## 完成证据

- Focused 最终相关回归 86 项通过；Fast 为 667 passed、8 deselected，全仓 Ruff
  format/lint、7 个相关生产模块 mypy、宿主 Docker 配置和完整差异检查通过。
- 固定 revision 证据白名单、跨上下文端口、两步崩溃恢复、首个 reason、单拒绝/单事件、
  普通失败手动重试和敏感信息边界审计收敛，无剩余 P0/P1/P2。
- Compose Final 第二次尝试通过：自包含 667 passed、8 deselected，PostgreSQL
  integration/E2E 102 passed、15 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启
  持久性、ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。

**依赖**: TASK-104

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-106.md"`
