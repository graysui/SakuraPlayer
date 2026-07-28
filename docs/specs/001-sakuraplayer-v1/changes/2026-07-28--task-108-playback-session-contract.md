# Change Specification: TASK-108 播放会话契约闭合

**Type**: Delta
**Date**: 2026-07-28
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-107 已交付最小 playback session/lease Schema，但 TASK-108 的已冻结 OpenAPI 没有为
分段媒体定义逐段能力地址，并提前承诺 TASK-109 的 compatibility/HLS 与 TASK-111 的进度。
平台固定 UA 也只有规则没有字面值。本变更闭合这些边界，不增加 HLS、字幕下载或影片进度行为。

## ADDED

### 固定平台 User-Agent

共享常量固定为：

| 平台 | 值 |
|---|---|
| Windows | `SakuraPlayer/1.0 (Windows; x64)` |
| HarmonyOS | `SakuraPlayer/1.0 (HarmonyOS; API 24)` |

会话创建和 stream 请求都按 platform 选择并精确比较该值；Cloud115 downurl 使用同一值。它们是
协议常量，不接受客户端覆盖。TASK-213/TASK-312 仍负责真实设备和真实 115 的外部门禁。

### 分段队列会话投影

创建请求携带 `client_instance_id`、所选候选组中的入口 `media_id`、`platform` 和当前仅允许的
`original` mode。服务端锁定 ready CacheJob，验证入口媒体属于完整有序选择，并为该选择中的每个
媒体在同一事务中创建独立的 12 小时 PlaybackSession 和该 client 的 lease。清单的入口字段
`session_id/stream_url` 指向请求的入口媒体；`media_queue` 按选择 `sequence_no` 返回每段的
`session_id/media/stream_url`。所有 session 使用同一签发时间、过期时间和平台 UA。

这使客户端可以顺序播放分段而不猜测 URL；上游 URL 仍只在每次 stream 302 调用栈中存在，绝不
进入数据库、日志、事件或测试快照。

### 阶段能力与错误映射

- TASK-108 的创建接口只接受 `original`。`compatibility` 和 HLS fallback 是 TASK-109 的唯一
  所有者，TASK-108 不调用 `resolve_hls`。
- Manifest 在 TASK-111 前返回 `progress: null`，保持字段形状稳定而不伪造进度。
- original stream 映射：credentials expired `422`、file not found `404`、original unavailable
  `422`、rate limited `429`（转发有界 Retry-After）、unavailable `503`、protocol error `502`。
  detached/cleanup 竞争继续为 `409 playback_media_detached`。

## MODIFIED

- REQ-019/AD-007 明确 TASK-108 只交付原画，TASK-109 再扩展兼容播放。
- PlaybackManifest 的 media_queue 从没有能力地址的 RemoteMedia 数组改为逐段 PlaybackQueueItem；
  progress 允许 null。
- TASK-108 的 DoR、实现上下文、测试边界及 OpenAPI 反映 client lease、分段会话和完整错误响应。

## Acceptance Criteria

- [x] 两个平台的固定 UA 可由后端、Cloud115 适配器和客户端共享，不存在未冻结字面值。
- [x] 有序分段选择能唯一投影为逐段签名 stream URL。
- [x] TASK-108 不提前实现 HLS/compatibility 或虚构影片进度。
- [x] 原画入口的所有 Cloud115 稳定错误均有声明的 HTTP 映射。
- [x] session、lease、TTL 刷新与 cleanup 使用同一个 CacheJob 行锁边界。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-019、技术计划 AD-007 | MODIFIED | MEDIUM |
| Cloud115/REST/错误码契约 | MODIFIED | HIGH |
| Playback session API/service | ADDED | HIGH |
| TASK-108/109/111 边界 | MODIFIED | MEDIUM |

## Testing Strategy

- 单元覆盖固定 UA、HMAC 字段篡改、12 小时边界、epoch、每次点击新 session 及原画错误映射。
- 集成覆盖完整分段队列、owner/cache/media/UA 拒绝、lease/cleanup 串行化、302/no-store、无代理
  视频字节和短链接持久化扫描。
- 默认测试只使用 FakeCloud115；真实协议和设备可用性保持外部门禁。

## Task Impact

不新增或拆分任务。TASK-108 实施该变更；TASK-109 扩展 HLS/compatibility；TASK-111 用真实进度
替换 manifest 的 null 占位。
