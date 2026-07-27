# Change Specification: TASK-105 媒体解析确定性边界

**Type**: Delta
**Date**: 2026-07-27
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-105 预审确认 TASK-104 已能把完成任务推进到 `resolving` 并保存 `task_dir_cid`，但实际
`Cloud115Adapter.list_files_recursive` 仍只枚举单层且隐藏子目录；视频白名单、256 MiB
边界、广告/样片词元、分段连续性、可解释评分和自动选择置信门槛也未冻结。直接实现会漏掉
嵌套媒体、把相近候选误判为主视频，或让 `awaiting_selection` 在目录 availability 中伪装
成可播放 `ready`。本变更只补齐 AC-035、AC-092、AC-093、AC-108、AC-109 的确定性实施
边界，不增加播放会话、下载字幕、TTL/LRU 或清理功能。

## ADDED

### 有界递归与目录归属

- `list_files_recursive(task_dir_cid)` 必须从任务目录开始按目录层级和上游稳定文件名顺序遍历，
  分页时包含直接子目录并继续枚举；只向调用方 yield 文件，不把目录伪装成媒体。
- 每个目录逐页固定 `limit=1000`，页内数量、声明总数、直接 `parent_cid`、重复目录 CID 和空页
  均须校验。固定最多 16 层、1024 个目录、100000 个文件；越界或目录环映射
  `cloud115_protocol_error`，不得返回部分成功结果。
- resolver 在枚举前后各调用一次 `directory_info(task_dir_cid)`，两次都必须证明 CID、任务目录
  名和直接父 CID 等于数据库快照；目录明确不存在或归属变化时原子进入 `detached`，不得写入
  部分媒体结果。

### 文件分类与真实 fixture

- 视频扩展名白名单固定为 `mp4/mkv/avi/mov/m4v/wmv/flv/ts/m2ts/webm`，按 Unicode NFKC、
  不区分大小写判断。文件必须有稳定 `file_id/pickcode/parent_cid`，`blocked` 不得为 true，
  且大小必须 **大于等于** 256 MiB；上游 `is_video` 只作为评分证据，不能绕过扩展名和大小。
- 字幕扩展名固定为 `srt/ass/ssa/vtt`，必须有稳定定位字段且大小为 1 byte..8 MiB；数据库只
  保存定位和匹配证据，不保存正文或短期 URL。
- 明显广告/样片只按规范化 stem 的独立词元排除，词元固定为
  `sample/trailer/preview/promo/advertisement/ads/cm/试看/試看/样片/樣片/预告/預告/广告/廣告`。
  词元必须由开头、结尾或非字母数字边界分隔，不能对子串命中。
- 正式 fixture 固定覆盖单正片、两个近似候选、嵌套目录、广告/样片、恰好 256 MiB、低 1 byte、
  blocked、重名、连续和缺段分段、四种字幕及过大字幕；默认测试不访问真实 115。

### 候选组、评分与字幕匹配

- 分段后缀只识别由 `. _ - 空格 [] ()` 分隔的 `cd/disc/disk/part/pt` 加 1..99 正整数，
  同一规范化基础 stem、扩展名和目录形成候选组。只有从 1 开始、无缺号、无重复且至少两段
  才是连续分段；否则各文件保持独立候选，禁止猜测队列。
- 每个媒体保存 `candidate_id`、组内 `sequence_no`、`selection_score` 和 JSONB
  `selection_evidence`。证据只允许稳定 reason/value，不保存短链、Cookie 或外部正文。
- 单媒体分数固定为：有效基础 10；上游 `is_video=true` 加 10；时长至少 1200 秒加 10；
  文件 stem 含影片规范化番号独立词元加 100；大小每满 256 MiB 加 1、最多 40。连续分段组
  以各段分数最大值加 20，组总大小只用于展示和确定性排序。
- 只有一个候选组时自动选中；多个候选时，只有唯一最高分且领先第二名至少 80 分才自动
  选中。其他情况进入 `awaiting_selection`，不得以文件最大、上游首项或 UUID 顺序猜测。
- 同名字幕先按 NFKC/casefold 后的完整 stem 与媒体 stem 匹配 100 分；剥离字幕尾部
  `zh/chs/cht/cn/中文` 后匹配 80 分；同一 parent CID 再加 10。未匹配字幕仍作为可选项保存，
  排序固定为匹配分降序、`srt/ass/ssa/vtt`、规范化名称、file ID。

### Schema 与选择事务

- TASK-105 迁移新增 `remote_media`、`remote_subtitle` 和
  `cache_job_media_selection`。媒体候选以 `candidate_id` 分组；同任务 file ID 唯一，候选内
  sequence 唯一；字幕的可空 `media_id` 必须与 `cache_job_id` 复合引用同任务媒体；选择表以
  `(cache_job_id, sequence_no)` 为主键且同任务 media ID 唯一。
- resolver 持久化文件快照、字幕、自动选择和 `resolving -> ready/awaiting_selection` 必须在
  同一 claim-fenced 事务完成；旧 token、取消竞态或目录移动后不得写回。
- 无有效视频进入 `failed`，错误码固定 `cache_no_valid_media`；协议/瞬时错误沿用
  Cloud115Port 错误，瞬时错误保留 `resolving` 并按 lease 退避。
- `PUT /cache-jobs/{id}/media-selection` 只接受 `awaiting_selection`。请求 media IDs 必须唯一、
  属于同一任务且恰好覆盖一个完整候选组；服务端按持久 sequence 排序后原子写选择并进入
  `ready`。跨任务、部分分段或混合候选返回 `409 state_conflict`。

## MODIFIED

- CacheJob 公开 DTO 的 `media_candidates/subtitles/selected_media_ids` 由真实持久数据投影；
  `RemoteMedia` 新增 `candidate_id`，不公开 pickcode、parent CID、score 或内部证据。
- `SourceAvailabilityPort` 只有 CacheJob 持久状态为 `ready` 时返回 `state=ready`，并把有序选择
  的 `size_bytes` 总和投影为 `video_file_size_bytes`。`awaiting_selection` 投影为 `running`；
  不得因为 ready 容量类别而提前声明可播放。
- TASK-105 只返回 CacheJob 中的有序 `selected_media_ids`。`PlaybackManifest`、播放会话和媒体
  队列 URL 投影仍由 TASK-108 所有。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| Cloud115 recursive adapter / fixture | MODIFIED | HIGH |
| RemoteMedia/RemoteSubtitle/selection Schema | ADDED | HIGH |
| resolving claim/worker | ADDED | HIGH |
| cache API / availability | MODIFIED | MEDIUM |

## Task Synchronization

本变更不创建或拆分正式任务。变更规格、迁移、实现、测试、TASK-105 状态、追踪矩阵和交接
进入 TASK-105 同一中文提交；TASK-107、TASK-108、TASK-110 和 TASK-112 的职责不提前实现。

## Testing Strategy

- 纯函数测试从固定真实命名 fixture 覆盖白名单、阈值、词元、评分、置信差、分段和字幕匹配。
- 适配器测试覆盖嵌套分页、空页、父 CID 欺骗、目录环及深度/数量上限。
- PostgreSQL 测试覆盖 0017 迁移、候选/选择唯一约束、resolving claim fencing、取消竞态、
  原子 ready/awaiting_selection、选择归属和 availability 实际大小。
- API/安全测试覆盖认证、额外字段、跨任务 media ID、部分分段、稳定错误和响应脱敏。
