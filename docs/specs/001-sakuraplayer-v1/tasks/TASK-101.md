---
id: TASK-101
title: "Cloud115Port、适配器与 Fake"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-015]
ac-mapping: [AC-013, AC-016, AC-017, AC-128, AC-129]
imp-requirements: [REQ-004, REQ-024]
cross-boundary: false
external-dependency-risk: true
provides: [Cloud115Port, protocol adapter, FakeCloud115, stable error mapping]
---

# TASK-101: Cloud115Port、适配器与 Fake

**功能描述**: 选择性移植已验证 115 SDK 原语，封装 Cloud115Port、稳定错误、敏感信息边界和可编排 Fake，不带入永久媒体库语义。

**规格映射**: AC-013、AC-016、AC-017、AC-128、AC-129

## 外部依赖风险

- **依赖**: 115 非官方扫码、目录、离线、直链和 HLS API。
- **状态**: `avmedia` 已有真实验证实现，但协议可变化。
- **缓解**: GPLv3 来源说明、历史 fixture、Fake 默认测试和显式 real-115 marker。

## 验收条件

- [ ] 端口覆盖扫码、凭据探活、目录、离线、文件枚举、原画、HLS、小文件下载和删除；支撑 AC-013。
- [ ] 凭据过期与临时 unavailable 使用不同稳定错误，不伪装成普通播放错误；对应 AC-016。
- [ ] 适配器日志/异常不暴露 Cookie、磁力或上游短链；对应 AC-017。
- [ ] 默认测试全部使用 Fake/fixture，并覆盖 115 状态机、签名相关原语和安全删除所需返回；对应 AC-128、AC-129。

## Definition of Ready

- [ ] TASK-015 完成且 Cloud115Port 契约已读取。
- [ ] 已确认移植文件的 GPLv3 来源声明方式。
- [ ] 不移植 MediaLibrary、copy/move 永久入库或外部播放器路径。

## 技术上下文

- 领域层只见稳定 DTO/异常；115 errno、JSON 和 RSA 细节留在 infrastructure。
- Cookie snapshot 回写接口由 TASK-102 使用。
- 原画/HLS URL 只在调用栈存在，禁止持久化。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/ports/cloud115.py` - 领域端口和稳定类型。
- `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/` - 移植 SDK 与适配器。
- `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/NOTICE.md` - 许可证和来源。
- `backend/tests/fakes/cloud115.py` - 可编排 FakeCloud115。
- `backend/tests/unit/cloud115/test_adapter_contract.py` - 类型/错误/脱敏合约。
- `backend/tests/lib/cloud115/test_protocol_fixtures.py` - 无网络协议样本。

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

- [ ] Cloud115Port/Fake/适配器和来源声明完成。
- [ ] 所有短期 URL 与秘密边界测试通过。
- [ ] 未引入旧永久媒体库产品模型。

**依赖**: TASK-015

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-101.md"`
