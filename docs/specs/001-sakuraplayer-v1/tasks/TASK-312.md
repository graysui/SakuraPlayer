---
id: TASK-312
title: "[已撤销] HarmonyOS API 24 真机前置门禁"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: cancelled
dependencies: []
ac-mapping: []
imp-requirements: []
cross-boundary: false
external-dependency-risk: false
provides: []
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-312: [已撤销] HarmonyOS API 24 真机前置门禁

本任务原计划在鸿蒙业务开发前增加 API 24 物理真机连接和播放门禁，现根据 2026-08-04 变更规格撤销。该文件保留用于说明历史任务编号，不再执行，也不再作为任何后续任务的依赖、DoR、DoD 或发布门禁。

**当前替代**: `TASK-301` 负责已安装 DevEco/SDK/Hvigor/ohpm/Node 工具链、Stage 工程、API 24 签名和构建基线；`TASK-310`/`TASK-311` 负责固定 UA、302、Range、HLS、MKV、ASS 的自动化 fixture 验证。API 24 仍是 SDK 和 API 签名基线，但不要求连接、授权或侧载物理真机。

## 状态

- [x] 已撤销物理真机连接和真机前置门禁要求。
- [x] 已从当前追踪矩阵、有效任务依赖和运行配置契约中移除。
- [x] 不创建历史任务原计划中的 probe 工程、真机门禁脚本或真实设备证据文件。

本历史任务不提供实现命令。
