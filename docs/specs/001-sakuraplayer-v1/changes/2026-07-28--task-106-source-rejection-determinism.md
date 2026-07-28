# Change Specification: TASK-106 来源拒绝确定性边界

**Type**: Delta
**Date**: 2026-07-28
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-106 预审确认，固定上游 revision 的真实离线任务响应只提供通用
`status=-1/status_text=下载失败`，无法证明来源永久失效、违规或无法离线。当前适配器还把
HTTP 400/422、缺失 `info_hash` 和通用 request errno 过宽映射为 invalid；直接据此拒绝会
不可逆清除仍可能有效的来源。本变更把初始确定性白名单缩小到固定 revision 已观察并反向
验证的提交 not-found errno，以及递归文件响应明确的 `ic=1` 违规标记，并冻结跨上下文调用、
崩溃恢复和事件幂等边界。

## Evidence

- 参考实现固定为 `tinypinglite/sakuramediabe` revision
  `670ca75b2d35b606ffc0caa6fd47fd04c4c95870`，不得以浮动版本扩展白名单。
- 该 revision 的 `OfflineTask` parser 注明匹配 2026-07-12 真实响应；失败任务只有
  `status=-1` 和通用 `status_text=下载失败`，没有稳定永久原因字段。
- 同一 revision 的离线实现记录已观察并反向验证的 not-found errno 集合
  `20121,20125,990002,4100003,4100008`；只有这些 errno 出现在离线提交端点时，适配器才
  输出稳定 `cloud115_source_unavailable`。
- 同一 revision 的递归文件响应字段 `ic=1` 明确表示违规封禁；适配器只投影为
  `RemoteFile.blocked=true`，不向领域暴露 `ic` 或原始正文。
- 上述固定 revision 的脱敏历史响应及 Fake 是 TASK-106 接受的真实 fixture 证据；默认测试
  不访问真实 115。

## ADDED

### 最小确定性白名单

| 稳定证据 | CacheJob failure code | SourceRejection reason |
|---|---|---|
| 离线提交端点返回固定 not-found errno | `cloud115_source_unavailable` | `cloud115_source_unavailable` |
| 任务目录任一远端文件 `blocked=true` | `cloud115_source_blocked` | `cloud115_source_blocked` |

- 分类器只接受以上稳定领域证据，不接受 errno、状态文案、HTTP 正文、磁力或任意 raw payload。
- 普通 `OfflineStatus.FAILED`、`status_text=下载失败`、HTTP 400/422、缺失 `info_hash`、
  errno `990005`、未知 errno、网络/429/5xx、配额、凭据过期和提交不确定均不得拒绝来源。
- 普通 remote failed 仍以 `cloud115_offline_failed` 结束当前 CacheJob；其他瞬时/不确定错误
  沿用 TASK-104 的 defer、failed 或 `submit_uncertain` 语义，来源保持可用。

### 跨上下文读取与拒绝顺序

- Resources 新增 `load_submission_ref(movie_id, source_id)`，只返回
  `source_id/website/external_post_id/rejection_reason_code?`，不解密磁力。只要来源身份仍属于该
  影片，即使已被拒绝也必须可读取该引用；已有 reason 只投影 Resources 首次保存的稳定码，
  使提交错误证据消失后仍能补齐 CacheJob 终态与事件。
- Cloud Cache 只能通过 `SourceSubmissionPort` 和 `SourceRejectionPort` 调用 Resources，禁止
  import Resources repository/model。
- 确定性证据处理顺序固定为：先读取非敏感引用，再幂等调用 `reject`，最后在 CacheJob 的
  claim-fenced 事务中写 `failed` 和 `cache.job.failed.v1`。
- 若进程在拒绝提交后、CacheJob 失败提交前崩溃，任务保留活动状态；claim 到期后再次领取，
  worker 在外部调用前读取已有稳定 reason，引用读取和拒绝均幂等，最终收敛到一个拒绝记录
  和一个失败事件。不得先把任务置为终态，否则任务不会再被领取，清磁力操作无法恢复。

### 事件所有权

- TASK-106 只提前写确定性来源拒绝对应的 `cache.job.failed.v1`；payload 固定为
  `id,status,error_code,rejected_source`，其中 `rejected_source=true`。
- CacheJob 状态和该事件必须在同一数据库事务提交。claim fencing 保证一次终态写入；重放
  不得产生第二个拒绝记录或第二个事件。
- TASK-112 实现完整 cache event publisher 时，不得回填或重复发布 TASK-106 已持久化的该
  事件；其他 CacheJob 事件仍由 TASK-112 所有。

## MODIFIED

- 离线提交 HTTP 400/422、缺失 `info_hash` 和 errno `990005` 映射
  `cloud115_protocol_error`；只有固定 not-found errno 映射
  `cloud115_source_unavailable`。
- resolver 在媒体扫描过滤前检查任一 `RemoteFile.blocked=true`。该证据必须先触发来源拒绝，
  不能被 scanner 隐藏后降级成 `cache_no_valid_media`。
- `SourceRejectionPort.reject` 继续只接收 `website/external_post_id/reason_code`；reason 必须来自
  本变更白名单，不携带磁力、errno、上游正文或可还原摘要。

## Schema Impact

现有 `source_rejection` 唯一约束、CacheJob claim 字段和 `domain_event` outbox 已满足原子性与
幂等需求；TASK-106 不新增迁移。

## Task Synchronization

本变更不拆分正式任务。变更规格、契约、实现、测试、TASK-106 状态、追踪矩阵和交接进入
TASK-106 同一中文提交。TASK-112 的通用 cache publisher 职责保持不变，但必须识别本变更的
既有确定性失败事件所有权。

## Testing Strategy

- 纯函数测试覆盖两个白名单输入，以及 remote failed、网络、429、5xx、未知、配额、凭据和
  submit uncertain 不命中。
- 适配器 fixture 测试覆盖固定 not-found errno、HTTP 400/422、缺失 `info_hash` 和 `990005`。
- PostgreSQL 集成测试覆盖清空磁力、导入 anti-join、重复处理、拒绝与失败之间崩溃后重领、
  单拒绝/单事件和临时失败保留来源。
- 数据库、事件、异常 repr 和安全快照扫描不得出现磁力或上游正文。
