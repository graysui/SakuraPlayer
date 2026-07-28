---
id: TASK-109
title: "最高码率 HLS 兼容播放"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
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

- [x] 默认原画；原画取链可回退错误或用户显式兼容模式时使用最高码率 HLS；对应 AC-101。
- [x] 客户端契约只出现 original/compatibility，不返回全部档位；对应 AC-103。
- [x] 后端 master 解析和选中 variant 绑定播放会话固定 UA；客户端 variant/segment 责任保持在 TASK-210/310 和真实门禁。
- [x] 凭据失效、媒体不存在等确定性错误不被吞成普通 HLS fallback。

## Definition of Ready

- [x] TASK-108 播放会话模式和 stream endpoint 可用。
- [x] HLS variant DTO、fallback error allowlist 和 no-store 规则由 [TASK-109 HLS 回退确定性边界](../changes/2026-07-28--task-109-hls-fallback-boundaries.md) 冻结。
- [x] Cloud115Adapter 已用无网络 fixture 交付 master 解析，播放层直接消费类型化 DTO。

## 技术上下文

- `compatibility` 每次创建新 session，不能修改已签名 mode。
- 选择 `max(bandwidth)`，同 bandwidth 保持 master 原顺序。
- 自动 fallback 白名单仅含 `cloud115_original_unavailable`；其他 original 错误保持原 code。
- Cloud115Adapter 负责协议解析；播放层验证 pickcode/UA/variants 并执行选择策略。
- 上游 HLS URL 只用于当次 302，不落库。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/playback/hls.py` - 类型化 HLS DTO 校验和最高 variant。
- `backend/src/sakuraplayer/playback/fallback_policy.py` - 原画可回退/不可回退错误。
- `backend/src/sakuraplayer/playback/resolver.py` - original/compatibility 分派。
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

- [x] 原画优先/HLS 兼容和错误策略完成。
- [x] UI 契约只有两种模式。
- [x] 固定 UA 与 no-store 测试通过。

## 完成证据

- Focused 最终为 29 项 playback 单元通过；Fast 为 720 passed、8 deselected，全仓 Ruff
  format/lint、6 个 playback 生产模块 mypy、宿主 Docker 配置、完整差异和只读审计通过。
- fallback 白名单、compatibility 新会话、最高 bandwidth/同码率首项、pickcode/UA 校验、HLS
  稳定错误、302 no-store、无档位列表与短链不持久化均有自动证据，无剩余 P0/P1/P2。
- Compose Final 第二次尝试通过：自包含 720 passed、8 deselected，PostgreSQL
  integration/E2E 105 passed、15 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启
  持久性、ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。

**依赖**: TASK-108

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-109.md"`
