# SakuraPlayer v1 实时事件契约

**版本**: 1.0.0

**WebSocket**: `GET /api/v1/events/ws?after_event_id={uuid}`

## 1. 连接规则

1. 握手必须携带有效 Bearer 访问令牌。
2. `after_event_id` 可选；存在时服务端从下一条仍保留的事件开始发送。
3. 游标过旧或不存在时用 close code `4409` 关闭，客户端先请求 `GET /api/v1/events/snapshot`。
4. WebSocket 只降低延迟。客户端首次启动、重连、切回前台和检测到 `stream_version` 跳号时必须以 REST 快照恢复。
5. 完全退出后客户端不维持后台连接；下次启动补拉任务和未读通知。

## 2. 信封

```json
{
  "version": 1,
  "event_id": "018f...",
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
| `stream` | 是 | `metadata/cache/credential/catalog/notification` |
| `stream_version` | 是 | 同聚合单调递增；跳号时拉快照 |
| `type` | 是 | 版本化事件名 |
| `occurred_at` | 是 | RFC 3339 UTC |
| `resource` | 是 | 脱敏后的完整或足够合并的资源快照 |

事件不包含 Cookie、磁力、AI key、Bearer/刷新令牌、完整播放 URL、115 上游 URL、字幕正文。

## 3. 事件类型

### 3.1 元数据

| type | 触发 | resource 最小字段 |
|---|---|---|
| `metadata.job.queued.v1` | 新任务入队 | `id,movie_id,number,priority,status,attempt_no` |
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
| `cache.job.ready.v1` | 可播放 | `id,status,selected_media_id,expires_at` |
| `cache.job.failed.v1` | 确定性失败 | `id,status,error_code,rejected_source` |
| `cache.job.cancelled.v1` | 取消并清理完成 | `id,status` |
| `cache.job.cleaned.v1` | TTL/LRU/手动清理完成 | `id,status` |
| `cache.job.cleanup_failed.v1` | 未确认删除 | `id,status,error_code,attempt_no` |
| `cache.job.detached.v1` | 目录被移动/归属不成立 | `id,status,error_code` |

60 秒客户端等待结束不产生事件，因为后端任务状态没有变化。

### 3.3 凭据和通知

| type | 触发 | resource 最小字段 |
|---|---|---|
| `credential.cloud115.changed.v1` | 绑定/重扫/失效 | `status,last_verified_at` |
| `notification.created.v1` | 可展示通知 | `id,type,resource_id,created_at` |
| `catalog.movie.core_ready.v1` | 核心元数据首次可见 | `movie_id,number` |

## 4. 客户端合并算法

1. `event_id` 已处理则忽略。
2. 同资源事件 `stream_version <= local_version` 则忽略。
3. `stream_version == local_version + 1` 时用 `resource` 替换对应快照。
4. 版本跳号、未知事件版本或本地没有资源时，拉对应 REST 快照。
5. 事件触发导航或通知，但不得自动开始播放；后台完成的缓存只进入 ready 并通知。

## 5. 心跳

- 客户端每 30 秒发送 `{"type":"ping","sent_at":"..."}` `(derived)`。
- 服务端返回 `{"type":"pong","sent_at":"...","server_at":"..."}`。
- 连续两个周期无响应时关闭并退避重连；重连后拉任务快照。

## 6. 兼容性

- 新增事件必须使用新的 `type`。
- 现有事件可以新增可选字段，不能删除或改变已有字段语义。
- 不认识的事件类型必须忽略并触发一次快照刷新，不能使客户端崩溃。
