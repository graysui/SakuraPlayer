# Windows 播放请求客户端契约

**Status**: Accepted
**Date**: 2026-07-31
**Owner**: TASK-209

本契约固定 Windows 对既有 `/api/v1/movies/{movie_id}/play-requests`、cache 事件/快照、TASK-202 通知端口和 `/player` 占位 route 的消费。后端状态机、幂等事实、60 秒不写失败和事件水位继续以 `rest-api.openapi.yaml`、`realtime-events.md`、TASK-103/104/112 契约为真相。

## 1. 播放请求 DTO 与 gateway

- `PlayRequestResult` 严格读取 `disposition`、可空 `wait_deadline` 和 `cache_job`；只接受 `ready/started/queued/reused`，`cache_job` 复用 TASK-202 的 `CacheJobDto`，不得复制或放宽状态枚举。
- 新建请求只接受 TASK-207 传入的 UUID `movie_id/source_id`；gateway 发送 `POST movies/{movie_id}/play-requests`、JSON `{source_id}` 和 `Idempotency-Key` header。Key 使用安全 ASCII，长度 `16..128`，每次用户动作生成一次并在请求重试/认证 refresh 中复用。
- `started` 必须是新建 `submitting` 任务且有 RFC3339 UTC `wait_deadline`；客户端把 deadline 与收到响应时的墙上时钟差转换为单调 deadline，并将剩余时间限制在 `0..60` 秒。`ready/queued/reused` 的 deadline 必须为 null。
- 200 表示 ready 或已有任务复用，202 表示新建 started/queued；HTTP 状态不是客户端唯一状态真相，必须同时解析 disposition 和 `cache_job.status`。

## 2. Controller 状态机

| 返回/事件 | 客户端动作 | 自动播放 |
|---|---|---|
| `ready` + `job.status=ready` | 复制 job/首媒体 ID 后进入 typed player route | 是，一次 |
| `started` + deadline | 进入 `/wait`，锁定普通导航 | deadline 前同 job ready 时是，一次 |
| `queued` | 立即退出等待，提示排队并保留 cache snapshot | 否 |
| `reused` + `ready` | 复制 job/首媒体 ID 后进入 typed player route | 是，一次 |
| `reused` + 非 ready | 提示任务已存在，等待后台事件/通知 | 否 |
| deadline 后收到 ready | 更新 snapshot 并触发通知 | 否 |

重复点击在请求在途时只保留一个本地请求；响应返回后再次点击同一 source 依赖服务端活动任务复用，不创建客户端预取或第二个后台请求。`awaiting_selection` 不在本任务内自动选择媒体，用户进入缓存页并按 [Windows 播放器客户端契约](windows-playback-client.md) 显式选择候选组。

ready 交接必须在 reset controller 前复制 `cache_job.id` 和首个 `selected_media_ids`；TASK-210
把既有无参数占位 route 替换为只含两个 UUID 的受认证 typed route。空选择不得导航或猜测媒体。

## 3. 阻断等待页

- `/wait` 只由当前 controller 的 `started` 状态进入；直接打开或 controller 没有匹配等待 job 时返回缓存页，不从 URL 推断播放能力或 deadline。
- 页面只显示任务状态、单调剩余秒数、固定 `2/10` 容量事实和取消按钮。不得显示磁力、Cookie、签名 URL、上游响应、速度调参或并发编辑控件。
- `PopScope` 和 Shell/route guard 阻止 back、左栏、全局搜索、缓存/设置和普通 URL 导航。取消按钮必须先二次确认，再发送 `POST cache-jobs/{id}/cancel` `{confirmed:true}`。
- 取消成功回到 `/app/cache`；`cache_active_lease`、`cache_cancel_confirmation_required` 或其他稳定错误保留等待页和服务端任务状态。超时退出等待只回到来源详情/缓存提示，不发送取消或失败请求。
- Windows 进程/窗口关闭不发送取消；任务继续由后端运行。下次启动先 REST snapshot，再连接 WebSocket；后台 ready 不能自动导航播放器。

## 4. 事件和快照

- Controller 只观察 `snapshotStateProvider` 的类型化 `CacheJobDto`，事件丢失或版本跳号由 TASK-202 快照恢复处理；不得直接把 event resource 当完整 job。
- 只有当前 controller 仍处于 `waiting`、job ID 相同且本地单调时间小于 deadline，`status=ready` 才产生一次 `ready` 导航。任何其他 ready 仅更新快照并通知。
- `cache.job.created/updated/selection_required/ready/failed/cancelled/cleaned/cleanup_failed/detached.v1` 不改变 60 秒本地计时；倒计时结束不产生事件。

## 5. Windows 通知

- `NotificationCoordinator` 继续负责未读筛选、串行投递和展示成功后 `PUT notifications/{id}/read`。平台 sink 不直接调用后端。
- 文案固定为：`cache_started`：“缓存任务开始”/“任务正在后台处理，不会自动播放”；`cache_ready`：“缓存已就绪”/“可在缓存页查看并播放”；`cache_failed`：“缓存任务失败”/“可在缓存页查看失败原因”；`credential_expired`：“115 凭据已失效”/“请在设置中重新扫码”。error code 只作为脱敏的补充文本，不展示上游正文。
- toast payload 只含后端 notification UUID；点击回调只导航 `/app/cache`，不带 source/movie 磁力参数，也不创建 play-request。展示调用成功才返回 `true`，异常或初始化失败返回 `false`，通知保持未读以便下次快照补拉。
- 使用 ADR-004 固定的 `flutter_local_notifications`，只调用即时 `initialize/show`；不调用 schedule、cancel、历史查询，不依赖 MSIX 包身份。完全退出不常驻。

## 6. 验证

- API/controller：四 disposition、deadline 0/1/59/60/迟到 ready、重复点击、queue/reused、取消确认、稳定错误和 snapshot 恢复。
- Widget/route：等待全屏锁、唯一取消出口、固定容量、长状态文本、窗口关闭说明和 `/player` 占位导航。
- 通知：四类文案、UUID payload、点击缓存页、sink 失败不标已读、无真实系统通知依赖。
