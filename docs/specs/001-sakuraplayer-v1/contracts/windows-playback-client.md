# Windows 播放器客户端契约

**Status**: Accepted
**Date**: 2026-07-31
**Owner**: TASK-210

本契约固定 Windows 对既有 CacheJob、playback session/manifest 和 media_kit 1.1.11 的消费。
后端签名、租约、原画/HLS resolver、字幕与进度真相继续以 OpenAPI、TASK-108 至 TASK-111 契约为准；
真实 115 的 302、Range 与 HLS 子请求由 TASK-213 验收。

## 1. 播放入口与 route

- ready job 必须有非空有序 `selected_media_ids`。详情直接 ready、等待期 ready 与缓存页 ready 都复制
  `cache_job_id` 和首个 `media_id` 后进入 `/player/:cache_job_id/:media_id`；复制完成后才 reset
  TASK-209 controller。
- route path 只包含 job/media 两个 UUID，不是播放能力。从详情发起的本次播放可额外携带可选
  `return_movie_id` UUID query；等待期 ready 必须在 reset controller 前复制同一 MovieId。缓存页播放不
  携带该 query。直接打开、参数非法或服务端判定 job/media 已失效时回到 `/app/cache` 并显示稳定错误；
  不得接受自由格式 return URL，也不得把来源 ID、标题、manifest、stream URL、UA、Cookie 或磁力写入 route。
- 播放器返回时，合法 `return_movie_id` 回到对应影片详情；缺失或非法时回到 `/app/cache`。返回动作
  只结束当前 Player 页面和其 session/lease，不取消或清理 CacheJob。
- 后台 ready、通知点击和 snapshot 更新只刷新缓存页。只有用户本次播放动作或 deadline 前仍等待同
  job 的 ready 才能进入 player route。

## 2. 歧义候选与缓存播放

- `awaiting_selection` 按 `RemoteMedia.candidate_id` 分组；组内只取 `is_valid=true` 项并按
  `sequence_no` 升序。候选行显示安全文件名、总大小、可用时长与分段数，不显示 pickcode/CID。
- 用户单选一个完整候选组并点击“选择并播放”，客户端向 media-selection API 提交该组全部 media
  UUID。响应必须为 ready 且选择非空，随后用首个 ID 进入播放器；在途时禁用重复提交。
- ready job 在缓存页显示播放图标按钮；cleanup 与 play 是独立显式动作。空选择、重复 sequence、
  无 valid media 或响应仍非 ready 视为 `client_protocol_error`，保留缓存页供刷新。

## 3. Session 与 manifest

- gateway 发送 `POST cache-jobs/{job}/playback-sessions`：
  `{media_id, mode, platform: windows, client_instance_id}`。每次进入、显式重试和模式切换都发送新请求。
- DTO 严格接受 `session_id/cache_job_id/mode/platform/stream_url/expires_at/
  subtitle_cache_expires_at/required_user_agent/embedded_tracks_source/media_queue/subtitles/progress`。
  TASK-210 校验结构但只消费播放队列和已有进度；字幕下载、轨道与心跳由 TASK-211 接入。
- manifest 必须匹配请求 job/mode、`platform=windows`、`embedded_tracks_source=client_player`、固定 UA，
  queue 非空且 session/media UUID 合法、`sequence_no` 严格递增。起始 media 必须存在于 queue。
- capability URL 以当前认证服务端 origin 解析，只接受同 origin HTTP(S) 的绝对 URL或 `/` 开头
  root-relative URL。完整 URL 只存在于 controller 和 Player 内存，不持久化或记录。

## 4. 固定 UA 与 media_kit

- Windows UA 常量固定为 `SakuraPlayer/1.0 (Windows; x64)`；manifest 返回其他值即协议错误，不能
  信任并透传任意 header。
- manifest 每个 queue item 映射为 `Media(absoluteUrl, httpHeaders: {'User-Agent': fixedUa})`，再以
  有序 `Playlist` 打开。stream URL 不附加 Bearer；后端 capability 自行校验签名和 UA。
- media_kit 1.1.11 的 Windows native `on_load` 会把 `Media.httpHeaders` 设置为 libmpv
  `http-header-fields`。自动测试证明每个 Media 的 header；TASK-213 证明真实 302/HLS 子请求链路。
- Player/VideoController 按页面生命周期创建并释放。认证失效、服务端切换或 route 退出时 dispose，
  清空 manifest、队列和错误订阅。

## 5. 模式与错误恢复

- 初始 mode 固定 `original`。菜单只有“原画”和“兼容播放”；切换到 `compatibility` 或切回 original
  都先创建新 session，成功后原子替换 manifest/playlist，失败保留旧会话和错误动作。
- original 的唯一自动 HLS fallback 在服务端流入口执行；客户端不解析 master、不选择档位，也不把
  普通 media_kit error 猜成 `cloud115_original_unavailable`。
- `Player.stream.error` 在 manifest 已到期时可为当前 generation 自动重新签发同 mode 一次；未到期
  错误显示“重试”和 original 下的“兼容播放”。自动重签失败或重复错误不得循环。
- gateway `ApiException.code` 原样进入脱敏 UI；协议/engine 字符串不显示上游 URL，不写普通日志。

## 6. Seek 与控制

- `ThrottlingPlayer` 只依赖 `Future<void> seek(Duration)` 端口。空闲时执行首目标；在途时只覆盖最后
  pending 目标；成功后执行该目标。失败清空 pending 并把异常交给 controller。
- slider `onChangeEnd`、键盘左右、前进/后退按钮和 TASK-211 后续自动续播只能调用 wrapper，禁止
  页面或默认 controls 直接访问 `Player.seek`。
- 页面使用自定义 media_kit controls，提供播放/暂停、进度 slider、当前位置/总时长、倍速菜单与
  全屏。控制区使用固定高度/可换行布局，窄窗口不得溢出；不创建缩略图请求、缓存或悬浮预览。

## 7. 验证

- DTO/API：未知字段、UUID、mode/platform/UA、queue 顺序、URL origin、client instance 与新 session。
- Controller：original、compatibility、失败保留、过期只重签一次、generation 隔离和 dispose。
- Seek：30 至 60 次连续目标、首尾、单次、失败清 pending、失败后新调用可恢复。
- Widget/route：三类 ready 入口、候选组选择、控制项、窄布局、无外部播放器与无缩略图。
