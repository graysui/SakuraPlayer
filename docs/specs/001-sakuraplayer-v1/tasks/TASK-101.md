---
id: TASK-101
title: "Cloud115Port、适配器与 Fake"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
completed_date: 2026-07-27
dependencies: [TASK-015]
ac-mapping: [AC-013, AC-016, AC-017, AC-128, AC-129]
imp-requirements: [REQ-004, REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [Cloud115Port, protocol adapter, FakeCloud115, stable error mapping]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-101: Cloud115Port、适配器与 Fake

**功能描述**: 选择性移植已验证 115 SDK 原语，封装 Cloud115Port、稳定错误、敏感信息边界和可编排 Fake，不带入永久媒体库语义。

**规格映射**: AC-013、AC-016、AC-017、AC-128、AC-129

## 外部依赖风险

- **依赖**: 115 非官方扫码、目录、离线、直链和 HLS API。
- **状态**: `avmedia` 已有真实验证实现，但协议可变化。
- **缓解**: GPLv3 来源说明、历史 fixture、Fake 默认测试和显式 real-115 marker。

## 验收条件

- [x] 端口覆盖扫码、凭据探活、目录、离线、文件枚举、原画、HLS、小文件下载和删除；支撑 AC-013。
- [x] 凭据过期与临时 unavailable 使用不同稳定错误，不伪装成普通播放错误；对应 AC-016。
- [x] 适配器日志/异常不暴露 Cookie、磁力或上游短链；对应 AC-017。
- [x] 默认测试全部使用 Fake/fixture，并覆盖 115 状态机、签名相关原语和安全删除所需返回；对应 AC-128、AC-129。
- [x] `OfflineTaskSnapshot` 不含磁力/source URL，异常不含 URL、Cookie、响应正文或 errno；对应 AC-017。

## Definition of Ready

- [x] TASK-015 完成且 Cloud115Port 契约已读取。
- [x] 已确认移植文件的 GPLv3 来源声明方式。
- [x] 不移植 MediaLibrary、copy/move 永久入库或外部播放器路径。

## 技术上下文

- 领域层只见稳定 DTO/异常；115 errno、JSON 和 RSA 细节留在 infrastructure。
- TASK-101 只产生 Cookie snapshot，不读取 credential_version 或数据库；加密 CAS 由 TASK-102 拥有。
- QR 固定 `alipaymini`，取消离线固定 `delete_source_files=False`；未知协议状态不得静默降级。
- 协议和能力 URL 只允许 Cloud115Port 契约列出的 HTTPS 115 主机并逐跳校验。
- 原画/HLS URL 只在调用栈存在，禁止持久化。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/ports/cloud115.py` - 领域端口和稳定类型。
- `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/` - 移植 SDK 与适配器。
- `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/NOTICE.md` - 许可证和来源。
- `backend/tests/fakes/cloud115.py` - 可编排 FakeCloud115。
- `backend/tests/unit/cloud115/test_adapter_contract.py` - 类型/错误/脱敏合约。
- `backend/tests/unit/cloud115/test_protocol_fixtures.py` - 默认 Fast/Final 收集的无网络协议样本。
- `backend/tests/real115/` - 仅显式 marker、开关、凭据和专属根齐全时运行的协议探针。

## 测试说明

**单元测试**:

- alive/expired/unavailable、目录 not-found、离线状态、限流、会员/HLS 未就绪映射。
- 日志捕获验证 Cookie、磁力、完整 URL 均不出现。

**集成测试**:

- Fake 编排扫码、Set-Cookie、提交不确定、多个视频/字幕、原画/HLS、目录移动和清理失败。
- 默认 pytest 不读取真实 Cookie，不访问 115。

**边界条件**:

- 协议字段缺失、未知 errno、密文解码失败、同 URL 并发 Range fixture。

## Definition of Done

- [x] Cloud115Port/Fake/适配器和来源声明完成。
- [x] 所有短期 URL 与秘密边界测试通过。
- [x] 未引入旧永久媒体库产品模型。

## Implementation Summary

- 新增精确 `Cloud115Port`、frozen DTO、稳定 `Cloud115Problem` 和可编排
  `FakeCloud115`；适配器覆盖 QR 四步、Cookie snapshot、凭据三态、目录、离线、
  递归枚举、原画、HLS、小文件和受管删除，并固定 HTTPS 主机、逐跳重定向、响应上限、
  逐操作错误映射和秘密脱敏边界。
- 只选择性适配固定参考 revision 的 downurl RSA/XOR 符号；未引入 upload AES/LZ4、
  rapid upload、copy/move、MediaLibrary、raw response 或 source URL。NOTICE 与根第三方
  声明记录上游 URL、revision、实际符号和 GPLv3。
- 默认协议验证使用 `tests/unit/cloud115/` fixture 和 Fake；真实只读探针位于
  `tests/real115/`，必须显式提供开关、Cookie 和应用专属测试根，且不进入默认 Fast/Final。
- Focused 最终 `38 passed`，镜像 readiness `6 passed`；Ruff format/lint、3 个生产文件
  渐进 mypy 和完整差异审计通过，Fast 最终 `504 passed, 8 deselected`。
- Compose Final 第一次因 test image 缺少正式 specs 退出；修复镜像输入并重过
  Focused/Fast/审计后，第二次通过自包含 `504 passed, 8 deselected` 和 PostgreSQL
  integration/E2E `88 passed, 15 deselected`。迁移、五服务健康、认证 canary、秘密扫描、
  重启、ready 降级恢复和隔离资源清理全部完成，默认 Final 未访问真实 115。

**依赖**: TASK-015

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-101.md"`
