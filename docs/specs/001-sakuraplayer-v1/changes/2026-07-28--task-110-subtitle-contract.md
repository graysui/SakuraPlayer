# Change Specification: TASK-110 字幕下载与生命周期边界

**Type**: Delta
**Date**: 2026-07-28
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-110 要求字幕下载前证明当前远端归属，并用缓存清理、退出登录和本地过期信号删除客户端
副本，但没有冻结 MIME、响应文件名、播放会话与字幕的授权关系，也把资源级事件职责与 TASK-112
重叠。本变更冻结可测试边界，不新增数据库表、Cloud115Port 方法或事件类型。

## ADDED

### Manifest 与授权集合

- `PlaybackManifest` 发布 `cache_job_id`、`subtitle_cache_expires_at` 和
  `embedded_tracks_source=client_player`；后端只发布外置字幕，不伪造内嵌字幕或音轨。
- 每个 `SubtitleOption` 发布可空 `media_id`。只允许 `media_id IS NULL` 或属于该 manifest 完整
  已选媒体队列的字幕进入 manifest。
- `media_id IS NULL` 的字幕可由同一 manifest 队列中的任一 playback session 下载；非空字幕只可
  由对应媒体的 playback session 下载。跨 owner、epoch、session、cache、未选媒体和字幕均统一返回
  `subtitle_not_found`，不泄露资源存在性。
- 本地字幕副本的服务端上限为 `subtitle_cache_expires_at`，固定等于 12 小时播放会话到期时间；
  客户端可以更早清理，不得延长。

### 下载响应

- API 必须使用 Bearer 认证；后端使用 playback session 平台对应的固定 User-Agent 获取小文件。
- 下载前必须实时证明缓存根仍是顶层 `SakuraPlayer-Cache`、任务目录仍是该根的直接子目录，
  并通过现有有界递归枚举确认目标 `file_id/pickcode` 当前仍在任务目录子树。数据库中的
  `parent_cid` 只作为扫描快照，不能单独充当当前归属证明。
- 数据库元数据和 Cloud115 小文件读取均执行 8 MiB 上限；成功响应原样返回字节，不转码、不探测
  字符集、不保存正文。
- MIME 固定为：`srt=application/x-subrip`、`vtt=text/vtt`、
  `ass/ssa=text/x-ssa`；不附加 charset。
- `Content-Disposition` 固定为 `attachment; filename="{subtitle_id}.{extension}"`，禁止把上游
  文件名放入响应头；同时返回 `Cache-Control: no-store` 和 `X-Content-Type-Options: nosniff`。

### 错误映射

- 远端文件/目录明确不存在、任务或根目录归属不成立、原画入口不可用统一映射
  `404 subtitle_not_found`。
- `cloud115_small_file_too_large` 映射 `413 subtitle_too_large`。
- 数据中出现非四格式映射 `422 subtitle_format_unsupported`。
- 凭据失效、限流、上游不可用和协议错误分别保持公开的
  `cloud115_credentials_expired/cloud115_rate_limited/cloud115_unavailable/cloud115_protocol_error`。

## MODIFIED

### 生命周期职责

- logout 继续使用已接受认证变更冻结的 `204`，表示调用客户端删除本机全部认证状态和字幕副本；
  TASK-110 不新增 logout 字幕事件。
- `cache.job.cleaned.v1` 仍由 TASK-112 发布；其既有 resource `id` 就是 cache job ID。客户端使用
  manifest 的 `cache_job_id -> subtitle_id` 映射删除对应副本，不要求事件重复列出 subtitle ID。
- 本地过期由客户端对 `subtitle_cache_expires_at` 执行；三类清理均不得影响永久图片缓存。

## Acceptance Criteria

- [x] manifest 明确内嵌轨道由客户端播放器枚举，并只发布当前已选媒体授权集合内的外置字幕。
- [x] 四格式下载具有固定 MIME、安全文件名、双重 8 MiB 上限、原样字节和 no-store/nosniff。
- [x] owner/session/cache/media 与实时远端归属均有自动测试，越权统一不泄露为 404。
- [x] logout、cache cleaned 和本地过期三种客户端清理责任无事件所有权冲突。
- [x] 任一字幕失败不撤销播放会话，也不阻止视频流解析。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-020 / TASK-110 | MODIFIED | HIGH |
| REST、错误码与事件契约 | MODIFIED | HIGH |
| TASK-112、211、311 | MODIFIED | MEDIUM |
| Playback manifest / subtitle API | MODIFIED | HIGH |

## Testing Strategy

- 单元覆盖字幕授权集合、稳定排序、四 MIME、安全文件名和格式/大小错误。
- 集成覆盖 owner/epoch/session/cache/media、实时 root/task/file 归属、凭据/限流/上游错误、
  原样字节、不落盘和字幕失败后视频仍可解析。
- 默认测试只使用 FakeCloud115，不访问真实 115。

## Rollback Plan

若实现未通过门禁，同时回退 TASK-110 代码、测试和本变更同步的契约；保持 TASK-105 的
RemoteSubtitle、TASK-108/109 播放接口、认证 logout 204 和 TASK-112 事件所有权不变。

## Task Impact

不新增或拆分任务。TASK-110 实现后端 manifest/下载契约；TASK-112 发布既有 cache cleaned
事件；TASK-211/311 枚举内嵌轨道、维护私有字幕缓存并执行三类清理信号。
