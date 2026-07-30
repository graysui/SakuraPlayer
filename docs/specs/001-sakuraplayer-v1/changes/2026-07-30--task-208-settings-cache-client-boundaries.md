# Change Specification: TASK-208 Windows 设置与缓存客户端边界

**Type**: Delta
**Date**: 2026-07-30
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-208 的 Definition of Ready 只列出二次确认、active lease 和秘密不回显，没有冻结五组实际 API 的严格 DTO、QR 轮询/释放、13 个缓存状态及操作白名单、对象级设置 CAS、诊断/元数据重试、route、generation 和响应式布局。核对实际后端还发现 `ProviderState.status` 可以返回 `not_configured`，冻结 OpenAPI 却遗漏该值。本变更修正契约冲突并补齐可执行的 Windows 客户端边界，不改变后端状态机或外部 115 行为。

## ADDED

### Windows 设置、QR、缓存与诊断确定性协议

- REQ-CHG-175: TASK-208 建立严格 settings/cache gateway，复用 TASK-202 的认证 ApiClient、snapshot 与共享 cache/metadata/binding DTO；新增 QR、capacity/page、settings、connection test 和 diagnostics DTO，未知枚举、范围、重复、秘密响应或非法路径均拒绝。
- REQ-CHG-176: QR 图片、session ID和轮询状态只保存在内存；离开流程、确认、过期、取消、认证变化或 dispose 时释放。waiting/scanned 固定 2 秒串行轮询，confirmed 只 confirm 一次，终态或上游错误停止自动轮询。
- REQ-CHG-177: 客户端严格区分 `cloud115_credentials_expired` 与 `cloud115_unavailable`；前者提示重新扫码，后者保留绑定并允许稍后重试。QR not-found/expired/canceled 提供重新扫码，不显示 Cookie、token、uid、sign、CID 或内部账号键。
- REQ-CHG-178: 缓存页消费 13 状态与固定 2/10/20 capacity。取消仅允许活动五状态并在二次确认后直接发送 confirmed=true；清理仅允许 awaiting_selection/ready/cleanup_failed。active lease、ownership mismatch 和在途操作按客户端契约保留权威任务。
- REQ-CHG-179: TTL 只允许 1..168 整数；20 ready、3 metadata 并发和 600 秒超时只读。设置更新遵循 JavDB/AI 对象级 replace/clear CAS，秘密输入不回显、不持久化并在提交/离页后清空。
- REQ-CHG-180: 连接测试只消费 target/status/error_code/elapsed_ms/checked_at；增量/全量同步只读展示。`unavailable` 不推断为 credentials invalid，worker/scheduler unknown 不伪造健康。
- REQ-CHG-181: 诊断只显示严格脱敏 component/queue/failure/connection test 字段。完整元数据 retry 只对 failed；富化 retry 只从服务端 retryable_stages 选择 images/dmm/actor_map/gfriends/translation，永不选择 javdb_core，translation 默认不选且必须显式确认。
- REQ-CHG-182: `/app/cache`、`/app/settings` 使用真实页面，并新增 `/app/settings/diagnostics` typed route。认证变化增加 generation、清空 QR/秘密/分页并忽略迟到响应；snapshot 状态变化触发缓存列表刷新而不以事件补丁代替完整分页。
- REQ-CHG-183: 页面 `<900px` 使用 16px、否则 24px 水平内边距，最大内容宽度 1280px。设置宽屏分区/窄屏 Tab、三类容量稳定几何、任务行最小 96px，所有状态有文字且危险操作二次确认。

## MODIFIED

- REQ-CHG-184: `ProviderState.status` 与实际后端统一为 `unknown/available/unavailable/credentials_invalid/not_configured`；OpenAPI 增加 `not_configured`，不改变已实现响应或连接测试状态。
- REQ-CHG-185: TASK-208 DoR 改为引用 [Windows 设置与缓存客户端契约](../contracts/windows-settings-cache-client.md)，以实际 API、错误码和对象级 CAS 为实施真相；文件清单补入 data/controller、diagnostics route 与严格测试。
- REQ-CHG-186: TASK-208 不实现 play-request、媒体选择、60 秒等待、播放器、Windows 系统通知或手动同步；这些职责继续归 TASK-209/210 或既有后端任务。

## Acceptance Criteria

- [ ] DTO/API 测试覆盖 QR、cache、settings、diagnostics、metadata retry 与 `not_configured`。
- [ ] Controller 测试覆盖 QR 生命周期、generation、分页/快照刷新、操作白名单、CAS 和重试阶段。
- [ ] Widget/route 测试覆盖宽窄布局、确认、秘密不回显、unknown/expired/unavailable 和 diagnostics route。

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-208 的依赖或 AC 映射。变更规格、客户端契约、功能规格、OpenAPI、Windows 任务索引、TASK-208 和追踪矩阵先独立提交；TASK-208 实现、测试、状态与交接在后续 TASK-208 中文提交中完成。

## Testing Strategy

- Dart 单元测试固定严格 DTO、gateway、QR/controller、分页、CAS 与错误动作。
- Flutter Widget/route 测试固定缓存、设置、诊断和响应式布局。
- Fast 运行 `dart format`、`flutter analyze` 和完整 `flutter test`；Final 运行 Windows debug build，不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-208 实现提交前可整体回退本变更。实现后只能通过新的前向变更调整客户端语义，不得放宽秘密、状态、CAS、清理或元数据阶段边界。
