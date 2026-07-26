# Catalog 与 Discovery 只读端口契约

**性质**: 后端内部跨上下文端口

## 1. 所有权

- 目录与元数据拥有 `core_ready` 影片、演员、标签、永久图片和聚合读取。
- 发现拥有全局搜索协调和影片/演员单一收藏；`FavoriteStatePort` 向目录读取提供批量收藏 ID，不允许目录直接读取 discovery 表。
- 115 播放缓存拥有来源 availability；播放拥有影片级 progress。
- API 只组合端口 DTO，不直接读取其他上下文未来表或外部 provider。

## 2. 来源可用性

```text
SourceAvailabilityPort.get_many(source_ids) -> {source_id: SourceAvailability}
```

`SourceAvailability` 只允许 `available/queued/running/ready/failed/rejected`，可选携带 `video_file_size_bytes`。未返回的活动来源按 `available` 处理；只有 `ready` 满足 `playable=true`。TASK-011 提供空实现，TASK-103/105 后续提供 PostgreSQL 适配器。

## 3. 影片进度

```text
PlaybackStatePort.get_many(movie_ids) -> {movie_id: PlaybackProgress}
```

未返回的影片进度为 null。`PlaybackProgress` 只含 `position_seconds/duration_seconds/completed/version`。TASK-011 提供空实现，TASK-111 后续提供持久适配器。

## 4. 搜索补全

```text
MetadataCompletionPort.ensure_search_priority(movie_id, normalized_number, sort_date)
  -> MetadataCompletion(job_id, state)
```

- 无 attempt：创建 `priority=10, reason=manual_or_search`。
- queued：在同一事务中提升为 priority 10 并改为 manual_or_search。
- running：原样复用，state 为 running。
- 最近 attempt 为 failed：不创建 attempt，state 为 failed。
- 在目录首次读取与 attempt 加锁之间变成 core_ready 时，端口向协调器返回内部 `completed` 信号；协调器刷新正式结果，`completed` 不进入公开补全占位。

## 5. 目录读取

发现只能通过目录查询服务读取安全 DTO。端口响应禁止磁力、上游正文、provider/translation 内部事实、claim 字段和文件系统绝对路径。所有批量端口输入和公开集合上限为 100。

永久图片 DTO 使用 `/api/v1/catalog/images/{image_id}`；图片读取端点按 ID 和受管根解析文件，不把 `relative_path/source_url` 公开给客户端。

## 6. 收藏状态

```text
FavoriteStatePort.target_ids(target_type) -> set[target_id]
```

发现实现 PostgreSQL 适配器和幂等写服务。目录只消费目标 ID 集合生成 favorite 字段和 `favorite=true` 过滤，不 import discovery ORM 模型。
