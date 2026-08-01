---
id: TASK-220
title: "Windows 启动初始化恢复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: dart
status: completed
dependencies: [TASK-202, TASK-219]
ac-mapping: [AC-135]
imp-requirements: [REQ-025]
cross-boundary: false
external-dependency-risk: false
provides: [bounded auth initialization recovery]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-220: Windows 启动初始化恢复

**功能描述**: 修复 Windows 读取本机安全存储时无限转圈且服务端地址不可输入的问题，使初始化超时或异常后可安全回到手工配置。

**实施边界**: [Windows 启动初始化恢复](../changes/2026-08-01--windows-startup-recovery.md)

## 验收条件

- [x] 认证初始化具有可测试的总超时，生产默认 5 秒；超时后进入中文 `serverRequired` 恢复状态。
- [x] 本机安全存储或地址读取抛出未预期异常时清除 busy，不暴露底层异常或本机内容。
- [x] 初始化期间服务端地址可输入，但地址提交和私网 HTTP 确认保持禁用，避免与初始化并发写入。
- [x] 恢复过程不清除保存地址、令牌、客户端实例 ID、字幕或私有缓存；手工配置仍执行既有 AC-135 规则。
- [x] 超时后的迟到初始化不能覆盖恢复状态或新地址；手工配置的本机存储失败也必须清除 busy。
- [x] Windows 安全存储在可终止后台 isolate 执行，不同步阻塞 UI，也不修改失败前的存储文件。

## Definition of Ready

- [x] TASK-202、TASK-219 已完成。
- [x] Windows 真实启动已复现持续转圈，后端 ready 200，阻断收敛到认证初始化前段。
- [x] Accepted Delta 已冻结初始化超时、中文恢复和交互边界。

## 实现批次

1. 初始化超时/异常状态机与聚焦控制器测试。
2. 初始化期间地址编辑、提交禁用与 Widget 测试。

## Definition of Done

- [x] Focused/Fast、完整差异审计和 Windows Final 全部通过。
- [x] 直接启动 Windows Release，实际确认不再持续转圈且地址提交按钮可点击。
- [x] TASK-217 与 TASK-214 保持 pending，交接和追踪矩阵同步。

**依赖**: TASK-202, TASK-219
