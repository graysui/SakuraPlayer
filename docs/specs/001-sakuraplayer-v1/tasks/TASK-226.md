---
id: TASK-226
title: "115 离线确认及时性与协议兼容修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-101, TASK-104, TASK-105, TASK-112]
ac-mapping: [AC-084, AC-086, AC-087, AC-088, AC-089, AC-090, AC-091]
imp-requirements: [REQ-017, REQ-018]
cross-boundary: false
external-dependency-risk: true
provides: [timely Cloud115 offline confirmation, compatible offline status parsing]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-226: 115 离线确认及时性与协议兼容修复

**功能描述**: 修复真实运行中 115 已快速完成但 worker 长时间才确认，以及离线任务状态解析/提交对账失败的问题。任务只调整后端观察反馈和 Cloud115 适配器兼容边界，不改变客户端 60 秒等待安全语义或提交不确定禁止自动重试的规则。

**实施边界**: [TASK-226 115 离线确认及时性与协议兼容](../changes/2026-08-03--task-226-cloud115-offline-confirmation.md)

## 验收条件

- [x] 离线仍在进行时的下一次确认间隔不超过 2 秒，cache worker 空闲等待不再叠加 5 秒固定延迟。
- [x] 115 数字/字符串等价状态和已批准字段别名正确归一化；未知状态仍稳定失败，不猜测完成。
- [x] `submit_uncertain` 只安全对账，不重复提交；无唯一匹配时取消仍回到 `submit_uncertain`。
- [x] `11c8de8b` 类 offlining 协议失败和 `394a1904` 类 submit uncertain 行为有脱敏回归测试覆盖。
- [x] 不改变 2/10 容量、claim fencing、60 秒客户端观察、迟到 ready 通知和默认无真实 115 测试边界。

## Definition of Ready

- [x] 用户已明确报告播放确认延迟和两个失败任务；现场只读状态已复核。
- [x] TASK-101/104/105/112 已 completed，Cloud115Port、offline worker、解析器和事件契约可用。
- [x] 已创建并接受本任务 Delta，未静默修改冻结规格。
- [x] 失败 fixture、聚焦测试和 Final 验证命令已准备。

## 实施批次

1. 以真实故障形状补齐 adapter 和 worker 的失败测试，固定不重复提交和未知值拒绝。
2. 实现 2 秒离线确认反馈、1 秒 cache 空闲轮询和安全状态归一化。
3. 运行 Focused/Fast，检查完整差异、秘密边界和只读审计。
4. 运行一次 Final，更新契约、任务索引、追踪矩阵和交接。

## 完成证据

- `Focused`: 受影响 worker/adapter 回归 28 项通过。
- `Fast`: Ruff 全仓 format/check、宿主 Docker 配置、858 项自包含测试通过（9 项按既有 marker 排除），`git diff --check` 通过。
- `Final`: `backend/tests/run-compose.ps1` 通过；858 项自包含测试通过（9 项按既有 marker 排除），128 项 PostgreSQL integration/E2E 通过（16 项按既有 marker 排除），迁移、四服务健康、认证、秘密日志扫描、重启、ready 降级恢复和隔离 Docker 资源清理完成。
- 故障覆盖：`11c8de8b` 类 `cloud115_protocol_error/offlining` 与 `394a1904` 类 `cloud115_submit_uncertain` 均由脱敏 fixture/regression 测试覆盖；默认测试未访问真实 115。

## 预计实现文件

**修改**:

- `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/adapter.py` - 离线状态/字段兼容归一化。
- `backend/src/sakuraplayer/cloud_cache/worker/claim.py` - 离线轮询反馈延迟。
- `backend/src/sakuraplayer/worker/__main__.py` - cache worker 专用空闲等待。
- `backend/tests/unit/cloud115/test_protocol_fixtures.py`、`backend/tests/unit/cloud115/test_adapter_contract.py` - 协议兼容回归。
- `backend/tests/unit/cloud_cache/test_offline_worker.py`、`backend/tests/unit/worker/test_worker_main.py` - 轮询与不确定对账回归。
- `docs/specs/001-sakuraplayer-v1/contracts/cloud115-port.md`、任务索引、追踪矩阵和 `SESSION-HANDOFF.md` - 契约及生命周期同步。

## Definition of Done

- [x] 所有验收条件、Focused/Fast/Final 和完整差异审计通过。
- [x] 任务状态、实现证据、契约、索引、追踪矩阵和交接文档同步。
- [x] 只暂存 TASK-226 相关文件并创建一次中文 Git 提交。

**依赖**: TASK-101, TASK-104, TASK-105, TASK-112
