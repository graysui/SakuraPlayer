---
id: TASK-109
title: "最高码率 HLS 兼容播放"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-108]
ac-mapping: [AC-101, AC-103]
imp-requirements: [REQ-019]
cross-boundary: false
external-dependency-risk: true
provides: [HLS compatibility resolver, original fallback policy]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-109: 最高码率 HLS 兼容播放

**功能描述**: 在原画取链失败或用户选择兼容播放时解析 115 HLS，按固定 UA 选择最高 bandwidth variant，并只暴露“原画/兼容播放”模式。

**规格映射**: AC-101、AC-103

## 外部依赖风险

- **依赖**: 115 VIP video info、master m3u8 和转码状态。
- **状态**: HLS 受会员、转码和 UA 约束。
- **缓解**: 会员/未就绪/非视频稳定错误、fixture master parser、同 UA、真实 HLS 门禁。

## 验收条件

- [ ] 默认原画；原画取链可回退错误或用户显式兼容模式时使用最高码率 HLS；对应 AC-101。
- [ ] 客户端契约只出现 original/compatibility，不返回全部档位；对应 AC-103。
- [ ] HLS 取 master/variant/segment 的 UA 与播放会话固定 UA 一致。
- [ ] 凭据失效、媒体不存在等确定性错误不被吞成普通 HLS fallback。

## Definition of Ready

- [ ] TASK-108 播放会话模式和 stream endpoint 可用。
- [ ] HLS variant DTO、fallback error allowlist 和 no-store 规则冻结。
- [ ] 参考 `Cloud115HlsService` 的解析 fixture 可移植。

## 技术上下文

- `compatibility` 每次创建新 session，不能修改已签名 mode。
- 选择 `max(bandwidth)`，同 bandwidth 保持 master 原顺序。
- 上游 HLS URL 只用于当次 302，不落库。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/playback/hls.py` - master 解析和最高 variant。
- `backend/src/sakuraplayer/playback/fallback_policy.py` - 原画可回退/不可回退错误。
- `backend/tests/unit/playback/test_hls_resolver.py` - variant/会员/转码 fixture。
- `backend/tests/integration/playback/test_compatibility_redirect.py` - 模式和 302。

## 测试说明

**单元测试**:

- 多 variant、同码率、空列表、VIP required、transcoding/not-video。
- allowlist 中原画错误回退，auth/not-found/owner 错误不回退。

**集成测试**:

- original 成功不调用 HLS；original 可回退失败调用最高 HLS；用户 compatibility 直接 HLS。
- 响应不包含档位列表、Cookie 或持久上游 URL。

## Definition of Done

- [ ] 原画优先/HLS 兼容和错误策略完成。
- [ ] UI 契约只有两种模式。
- [ ] 固定 UA 与 no-store 测试通过。

**依赖**: TASK-108

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-109.md"`
