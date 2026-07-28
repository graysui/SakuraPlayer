# SakuraPlayer v1 实时事件契约

**版本**: 1.1.0

**WebSocket**: `GET /api/v1/events/ws?after_event_id={uuid}`

## 1. 连接规则

1. 握手必须携带有效 Bearer 访问令牌。
2. `after_event_id` 可选；服务端先把仍保留的 event ID 解析为全局 `sequence`，再按 `sequence ASC` 从下一条发送。
3. 游标不存在或已超过固定 30 天保留窗口时用 close code `4409` 关闭，客户端先请求 `GET /api/v1/events/snapshot`。
4. WebSocket 只降低延迟。客户端首次启动、重连、切回前台和检测到 `stream_version` 跳号时必须以 REST 快照恢复。
5. 完全退出后客户端不维持后台连接；下次启动补拉任务和未读通知。

## 2. 信封

```json
{
  "version": 1,
  "event_id": "018f...",
  "sequence": 1042,
  "stream": "cache",
  "stream_version": 8,
  "type": "cache.job.updated.v1",
  "occurred_at": "2026-07-24T08:00:00Z",
  "resource": {
    "id": "018f...",
    "status": "offlining",
    "remote_percent": 37.5
  }
}
```

| 字段 | 必填 | 规则 |
|---|---|---|
| `version` | 是 | 信封版本，v1 固定为 `1` |
| `event_id` | 是 | 全局唯一 UUID，可用于去重和游标 |
| `sequence` | 是 | 数据库生成的全局单调 bigint；用于追赶和 REST 快照水位 |
| `stream` | 是 | `metadata/cache/credential/catalog/notification` |
| `stream_version` | 是 | 同聚合单调递增；跳号时拉快照 |
| `type` | 是 | 版本化事件名 |
| `occurred_at` | 是 | RFC 3339 UTC |
| `resource` | 是 | 脱敏后的完整或足够合并的资源快照 |

事件不包含 Cookie、磁力、AI key、Bearer/刷新令牌、完整播放 URL、115 上游 URL、字幕正文。
事件写入时固定 `expires_at=occurred_at+30 days`。`expires_at` 是服务端持久字段，不进入公开信封；清理只删除已过期事件。

## 3. 事件类型

### 3.1 元数据

| type | 触发 | resource 最小字段 |
|---|---|---|
| `metadata.job.queued.v1` | 新任务入队 | `id,movie_id,number,priority,status,attempt_no,retry_mode,requested_stages,parent_job_id` |
| `metadata.job.started.v1` | worker 领取 | 上述字段 + `stage,started_at` |
| `metadata.job.stage_changed.v1` | stage 变化 | `id,status,stage,stage_status,elapsed_ms` |
| `metadata.job.completed.v1` | 完成或带 warning 完成 | `id,movie_id,status,warnings,finished_at` |
| `metadata.job.failed.v1` | 失败/600 秒超时 | `id,movie_id,status,error_code,stage,elapsed_ms` |

失败事件不会触发自动重试。管理员手动重试会产生新的 job ID 和新的 `queued` 事件。

### 3.2 缓存

| type | 触发 | resource 最小字段 |
|---|---|---|
| `cache.job.created.v1` | 播放请求创建任务 | `id,movie_id,source_id,status,disposition` |
| `cache.job.updated.v1` | 离线/解析进度变化 | `id,status,remote_percent,error_code,updated_at` |
| `cache.job.selection_required.v1` | 多视频需选择 | `id,status,media_candidates` |
| `cache.job.ready.v1` | 可播放 | `id,status,selected_media_ids,expires_at` |
| `cache.job.failed.v1` | 确定性失败 | `id,status,error_code,rejected_source` |
| `cache.job.cancelled.v1` | 取消并清理完成 | `id,status` |
| `cache.job.cleaned.v1` | TTL/LRU/手动清理完成 | `id,status` |
| `cache.job.cleanup_failed.v1` | 未确认删除 | `id,status,error_code,attempt_no` |
| `cache.job.detached.v1` | 目录被移动/归属不成立 | `id,status,error_code` |

60 秒客户端等待结束不产生事件，因为后端任务状态没有变化。

TASK-106 只为确定性来源拒绝提前持久化 `cache.job.failed.v1`，并固定
`rejected_source=true`；CacheJob failed 与事件在同一 claim-fenced 事务提交。TASK-112 建立
通用 cache publisher 时不得回填或重复发布这一既有事件，其他缓存事件仍由 TASK-112 负责。
`cache.job.cleaned.v1.resource.id` 是客户端字幕清理使用的 cache job ID；subtitle ID 集合来自
PlaybackManifest 的映射，事件不重复携带。logout 204 和本地过期不产生资源级事件。

### 3.3 凭据和通知

| type | 触发 | resource 最小字段 |
|---|---|---|
| `credential.cloud115.changed.v1` | 绑定/重扫/失效 | `status,last_verified_at` |
| `notification.created.v1` | 可展示通知 | `id,type,resource_id,created_at` |
| `catalog.movie.core_ready.v1` | 核心元数据首次可见 | `movie_id,number` |

## 4. 客户端合并算法

1. `event_id` 已处理或 `sequence <= snapshot_version` 则忽略。
2. 同资源事件 `stream_version <= local_version` 则忽略。
3. `stream_version == local_version + 1` 时用 `resource` 替换对应快照。
4. sequence 或聚合版本跳号、未知事件版本或本地没有资源时，拉对应 REST 快照。
5. 事件触发导航或通知，但不得自动开始播放；后台完成的缓存只进入 ready 并通知。

## 5. REST 恢复快照

- 服务端在同一数据库事务内读取已分配的最大事件 sequence 和业务状态；该 sequence 是 `snapshot_version`。水位事件仍在 30 天窗口内时返回对应 `last_event_id`，已清理时返回 null。
- Phase 1 的元数据任务最多返回 100 项，活动任务优先，其后为最近终态；同时返回全量状态计数。
- cache、credential 和 notification 通过有界扩展端口聚合。对应 Phase 尚未交付时返回空任务/通知、零计数和 `unbound` 凭据状态，不创建未来业务表。
- 客户端应用快照后，无游标重连 WebSocket，并只合并 `sequence > snapshot_version` 的事件。

## 6. 心跳

- 客户端每 30 秒发送 `{"type":"ping","sent_at":"..."}` `(derived)`。
- 服务端返回 `{"type":"pong","sent_at":"...","server_at":"..."}`。
- 连续两个周期无响应时关闭并退避重连；重连后拉任务快照。

## 7. 兼容性

- 新增事件必须使用新的 `type`。
- 现有事件可以新增可选字段，不能删除或改变已有字段语义。
- 不认识的事件类型必须忽略并触发一次快照刷新，不能使客户端崩溃。
