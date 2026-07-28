---
id: TASK-108
title: "签名播放会话与原画 302"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-102, TASK-105, TASK-107]
ac-mapping: [AC-099, AC-100, AC-102, AC-104, AC-105]
imp-requirements: [REQ-019]
cross-boundary: false
external-dependency-risk: true
provides: [playback session signing, original resolver, 302 stream endpoint]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-108: 签名播放会话与原画 302

**功能描述**: 创建 12 小时播放会话，绑定 owner/session epoch/cache/media/platform UA，默认解析 115 原画并以 `302 no-store` 直连。

**规格映射**: AC-099、AC-100、AC-102、AC-104、AC-105

## 外部依赖风险

- **依赖**: 115 downurl 与 CDN 对 UA/Range 的限制。
- **状态**: 已验证 URL 绑定 UA、同地址并发 Range 敏感。
- **缓解**: 签发和请求 UA 双校验、短链不缓存到数据库、Windows seek 合并契约和真实 Range 测试。

## 验收条件

- [ ] 每次点击重新签发 12 小时会话；对应 AC-099。
- [ ] Windows/HarmonyOS 固定各自 UA，取链与播放器请求一致；对应 AC-100。
- [ ] 流入口校验 owner/session epoch、HMAC、过期、UA、缓存归属后返回 `302` + `no-store`，不代理字节；对应 AC-102。
- [ ] 只支持应用内播放器，并发布 seek 合并约束；对应 AC-104、AC-105。

## Definition of Ready

- [ ] TASK-105 有 ready media/pickcode，TASK-107 最小 session Schema、ownership/lease 可用。
- [ ] 播放 HMAC 使用 `contracts/runtime-configuration.md` 中独立的 playback key，不复用设置或 JWT key；stream endpoint 能在无 Bearer header 时验证会话能力。
- [ ] Windows/HarmonyOS UA 常量已冻结。

## 技术上下文

- 签名载荷包含 session ID、epoch、mode、UA hash、expires；完整上游 URL 不落库/日志。
- stream endpoint 只返回 redirect，NAS 不转发视频 Range。
- 消费 TASK-107 已迁移的 playback_session/lease Schema；创建播放会话刷新 CacheJob
  last_accessed/expires 并创建租约。本任务不重复创建表。
- 创建会话和租约必须锁 CacheJob 并复核仍为 ready，与 TASK-107 清理选择串行化。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/playback/session.py` - 会话、签名和撤销。
- `backend/src/sakuraplayer/playback/original.py` - downurl 同 UA 解析。
- `backend/src/sakuraplayer/playback/stream_api.py` - 302/no-store 入口。
- `backend/src/sakuraplayer/playback/user_agents.py` - 两平台固定 UA。
- `backend/tests/unit/playback/test_signature.py` - 篡改/过期/epoch/UA。
- `backend/tests/integration/playback/test_original_redirect.py` - 归属、302 和无代理。

## 测试说明

**单元测试**:

- 修改 session/cache/media/mode/UA/expires 任一字段签名失败；logout epoch 后失效。
- 12 小时边界和每次点击生成新会话。

**集成测试**:

- Fake downurl 验证取链 UA 与请求 UA 完全相同、Location 不持久化、响应 no-store。
- 跨用户/跨 cache/media、detached、已清理、无租约和错误 UA 均拒绝。

**边界条件**:

- 直链过期、取链限流、并发请求同会话、后端重启。

## Definition of Done

- [ ] 签名、原画、owner、UA、302 和租约完成。
- [ ] 后端没有视频代理响应路径。
- [ ] 数据库/日志短链扫描为空。

**依赖**: TASK-102, TASK-105, TASK-107

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-108.md"`
