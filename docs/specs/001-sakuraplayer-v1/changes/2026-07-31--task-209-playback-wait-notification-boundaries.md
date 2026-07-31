# Change Specification: TASK-209 Windows 播放请求、等待与通知边界

**Type**: Delta
**Date**: 2026-07-31
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-209 的任务文件引用了已实现的后端播放请求和 TASK-202 通知端口，但没有冻结 Windows 对四种 disposition、服务器等待 deadline、重复点击、窗口关闭、等待 route 阻断和系统通知适配器的消费边界。本变更只补齐客户端契约，不改变后端 OpenAPI、缓存状态机、事件正文或播放器能力。

## ADDED

### Windows 播放请求与通知确定性协议

- REQ-CHG-187: TASK-209 只接受 TASK-207 明确输出的 `movie_id` 与 `source_id`，生成 16..128 字符安全 `Idempotency-Key`，向 `POST /api/v1/movies/{movie_id}/play-requests` 发送 `{source_id}`。选择来源或重复点击不能发送磁力、帖子 ID、标题或 availability。
- REQ-CHG-188: Windows 严格解析 `PlayRequestResult` 的 `disposition=ready/started/queued/reused`、可空 RFC3339 `wait_deadline` 和完整 `CacheJob`；未知字段形状、枚举、UUID、状态或 deadline 关系触发 `client_protocol_error`。`started` 只允许新建任务并必须有 deadline；其他 disposition 不携带 deadline。
- REQ-CHG-189: `ready` 或 `reused` 且 job.status 为 `ready` 只进入既有 `/player` 占位 route；`started` 进入 `/wait` 阻断 route。`queued`、`reused` 的非 ready 任务立即返回来源页/缓存提示，不自动播放、不创建第二个请求；`reused` 不凭客户端时钟重新制造 60 秒 deadline。
- REQ-CHG-190: 等待只使用服务端 `wait_deadline` 初始化，并以本地单调时钟倒计时，最大观察窗口为 60 秒。事件或快照在 deadline 前把同一 job 更新为 `ready` 才允许一次性导航播放器；deadline 后即使收到 ready 也只能保留缓存并通知，不导航、不写 failed。
- REQ-CHG-191: 等待 route 使用 `PopScope`/导航守卫阻断 back、侧栏、搜索、设置和其他页面导航。唯一离开等待的页面动作是取消按钮打开确认对话框并发送 `confirmed=true`；取消成功后回到缓存页，失败保留等待状态并显示稳定错误动作。Windows 操作系统关闭窗口不发送取消请求，进程退出后任务继续后台执行，下一次启动按快照恢复。
- REQ-CHG-192: `cache_started/cache_ready/cache_failed/credential_expired` 由 TASK-202 `NotificationCoordinator` 交给 Windows `AppNotificationSink`。文案只使用本地固定中文和稳定错误码，不显示磁力、Cookie、签名 URL 或上游正文；toast 点击只打开 `/app/cache`，不得自动播放。
- REQ-CHG-193: Windows 平台适配器固定采用 ADR-004 的 `flutter_local_notifications 19.5.0`/Windows 1.0.3；即时 `show` 调用完成视为展示成功并才标记后端已读。插件异常返回未展示，完全退出不建立常驻后台通知进程。

## MODIFIED

- REQ-CHG-194: TASK-209 Definition of Ready 改为引用 [Windows 播放请求客户端契约](../contracts/windows-play-request-client.md) 和 ADR-004；四项依赖、`PlayRequestResult`/`wait_deadline`、取消/窗口关闭和通知适配器不再留空。
- REQ-CHG-195: TASK-209 实现文件补入严格播放请求 gateway/controller、阻断等待页、通知文案/Windows sink、播放器占位导航和对应单元/Widget 测试；不提前实现 media_kit、字幕、进度或发布安装包。

## Acceptance Criteria

- [ ] DTO/gateway 测试覆盖四种 disposition、deadline、幂等键、重复点击和错误码。
- [ ] Controller 测试覆盖 ready/started/queued/reused、59 秒 ready、60 秒超时、迟到 ready、取消确认和窗口关闭语义。
- [ ] Widget/route 测试覆盖等待导航锁、唯一取消出口、2/10 固定容量显示和 ready/后台通知不自动播放。
- [ ] Windows sink 测试覆盖文案、payload、展示失败不标已读和通知点击只进入缓存页；不要求真实系统 toast。

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-209 的依赖或 AC 映射。变更规格、客户端契约、ADR、架构、功能规格、Windows 任务索引、TASK-209 和追踪矩阵先独立提交；TASK-209 实现、测试、状态与交接在后续中文提交中完成。

## Testing Strategy

- Dart 单元测试固定严格 DTO、gateway、deadline 单调时钟和通知文案/平台端口。
- Flutter Widget/route 测试固定等待阻断、确认取消、迟到事件、系统后台/重启快照和不自动播放。
- Fast 运行格式、`flutter analyze`、完整 `flutter test` 和差异/秘密检查；Final 运行 Windows debug build，不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-209 实现提交前可整体回退本变更。实现提交后只能通过新的前向变更调整播放等待或通知语义，不得绕过服务端 deadline、取消确认、幂等请求或后台不自动播放规则。
