# Change Specification: TASK-111 进度与心跳确定性边界

**Type**: Delta
**Date**: 2026-07-28
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-111 的 DoR 把尚不存在的 MoviePlaybackState 迁移当作前置条件，同时冻结契约没有完整定义
未知时长、无进度心跳、版本冲突和 lease 结束语义。本变更把 0019 迁移纳入 TASK-111，并冻结可由
Windows/HarmonyOS 一致实现的 expected-version CAS、完成边界和心跳事务。

## ADDED

### MoviePlaybackState 迁移与归属

- TASK-111 独占新建 0019 线性迁移和对应 ORM；每个 `movie_id` 至多一行，状态不关联 cache、source、
  media、subtitle 或 playback session，因此换源、缓存清理和字幕失败不得删除进度。
- 数据库状态 `version` 从 1 开始并严格递增；请求 `version` 是 expected current version。不存在状态时
  只接受 expected version 0 并创建 version 1；存在状态时只接受与当前 version 相等的请求，成功后
  服务端加 1。
- 版本不匹配返回 `409 progress_version_conflict`，`details.progress` 携带权威状态；冲突请求不得修改
  进度、lease 或 CacheJob TTL。

### 完成规则

- position 必须有限且大于等于 0；duration 必须为 null 或有限正数。未知时长使用 null，不能使用 0。
- position 为 0 或 duration 为 null 时 `completed=false`。否则当 `position / duration >= 0.95`，或
  `duration - position < 120` 秒时 `completed=true`；恰好剩余 120 秒不完成，position 大于 duration 时完成。
- 完成状态保存 `position_seconds=0` 并保留已知 duration；manifest、目录和进度 API 都返回该权威
  形状，所以下次播放从头。之后客户端以最新 version 上报未达到完成阈值的位置时可重新进入
  `completed=false`。

### 心跳事务

- Heartbeat 只要求 `playback_session_id` 和与登录会话相同的 `client_instance_id`；`progress` 可省略。
- `playing` 省略时视为 true。`playing=true` 在一个事务内锁 CacheJob/session/lease，续期 90 秒 lease、
  刷新 CacheJob TTL，并在携带 progress 时执行影片状态 CAS。
- `playing=false` 不续期 TTL，在同一事务内先执行可选进度 CAS，再结束对应 lease；响应
  `lease_expires_at=null`。暂停/退出也可调用影片进度 PUT 单独 flush，不要求伪造心跳。
- 心跳必须验证 Bearer owner/session epoch、client instance、会话未撤销且未过期、CacheJob 仍 ready；
  任一不成立返回 `409 state_conflict`，且整个事务不产生部分写入。
- 心跳响应 `progress` 是该影片当前权威状态；尚无状态且本次未携带 progress 时为 null。

## MODIFIED

- `ProgressUpdate.duration_seconds` 改为可空但仍必填；`PlaybackHeartbeat.progress` 改为可选。
- `PlaybackProgress.duration_seconds` 只允许 null 或正数，`version` 是服务端状态版本且最小为 1。
- TASK-111 的 DoR 从“迁移已存在”改为“迁移结构与 CAS 已冻结”，由本任务创建迁移。
- 影片进度 PUT、manifest 和 Catalog 的 progress 使用同一只读投影，不新增观看历史列表 API。

## Acceptance Criteria

- [x] 0019 迁移和 ORM 约束 movie_id 唯一、数值范围、completed/position 形状和 version 下界。
- [x] 94.99%/95%、剩余 121/120/119 秒、未知时长、position 0 和 position 大于 duration 有测试。
- [x] expected version 0 首次创建、相等版本更新、旧/未来版本冲突及权威 details 有测试。
- [x] Windows/HarmonyOS client instance 读写同一 movie 状态；换源、清理和字幕失败不删除状态。
- [x] 无进度续租、携带进度原子续租、playing=false flush/end 和冲突全事务回滚有测试。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-013/020、TASK-111 | MODIFIED | HIGH |
| REST/错误码/数据模型契约 | MODIFIED | HIGH |
| Playback lease/session/manifest | MODIFIED | HIGH |
| Catalog progress port | MODIFIED | MEDIUM |
| TASK-211/311 client CAS | MODIFIED | MEDIUM |

## Testing Strategy

- 单元测试纯完成规则、数值校验、API DTO 和状态投影。
- PostgreSQL 集成测试迁移、CAS 并发、跨端、心跳/TTL/lease 原子性和独立生命周期。
- 默认测试使用本地数据库与现有 Fake，不访问真实 115。

## Rollback Plan

若实现未通过门禁，同时回退 TASK-111 代码、测试、0019 迁移及本变更同步的契约；保持 0018 的
playback session/lease、TASK-108 至 TASK-110 播放/字幕接口和 TASK-011 空进度端口不变。

## Task Impact

不新增或拆分任务。TASK-111 创建并消费影片进度 Schema；TASK-211/311 使用 expected-version CAS、
15 秒心跳和 pause/exit flush；不把后端完成规则重复实现在客户端作为权威判断。
